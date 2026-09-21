"""
Testes automatizados da app ``authentication`` (UniRota).

O que este arquivo cobre:

    1. Modelos / manager (User, UserManager, StudentProfile, User.avatar_url, can_invite)
    2. Formularios (UserRegistrationForm, StudentProfileForm, LoginForm, ChangePassword)
       e a classe de validacao de senha
    3. Fluxo publico de cadastro (signup) - caminhos felizes e caminhos de erro
    4. Login e logout
    5. Convites por e-mail para cargos elevados: geracao pelo service, envio do e-mail,
       consumo do link e verificacao de que o convite foi realmente consumido
    6. Area logada (settings, meus dados, avatar, troca de senha, notificacao)
    7. Reset de senha por e-mail (fluxo completo usando o link que sai em mail.outbox)
    8. Seguranca (CSRF, hashing de senha, enumeracao de usuarios, escalonamento de cargo)

As duas ultimas classes do arquivo documentam falhas encontradas no app:

    * ``FalhasUrgentesTests``          -> testes VERMELHOS de proposito (assertam o
      comportamento correto esperado). Cada docstring explica o problema atual.
    * ``FalhasAceitaveisParaMVPTests`` -> testes marcados com ``expectedFailure``
      (podem ser adiados, mas devem ser revisitados antes de producao).

Como rodar:

    python manage.py test authentication -v 2
"""
import re
import shutil
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest import expectedFailure
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import SESSION_KEY, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.signing import Signer
from django.db import IntegrityError, transaction
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from . import service
from .forms import (
    ChangePassword,
    LoginForm,
    StudentProfileForm,
    UserRegistrationForm,
    Validation,
)
from .models import StudentProfile, UserRole

User = get_user_model()

# Senhas usadas nos testes. Precisam respeitar o regex do app:
# 8+ caracteres, minuscula, maiuscula, numero e simbolo.
SENHA_FORTE = "Senha@123"
SENHA_NOVA = "NovaSenha@456"

# ---------------------------------------------------------------------------
# Ajuste de performance da bateria de testes
# ---------------------------------------------------------------------------
# O Django 6.1 usa PBKDF2 com 1.500.000 iteracoes por padrao (e, diferente de
# versoes antigas, o test runner nao troca mais o hasher automaticamente).
# A bateria cria/valida centenas de senhas, o que levaria muitos minutos.
# Durante os testes usamos o hasher MD5 (rapido) - o teste que verifica que a
# senha realmente fica hasheada com um algoritmo forte aplica
# @override_settings(PASSWORD_HASHERS=[PBKDF2PasswordHasher]).
settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def criar_usuario(
    email="aluno@unirotas.com",
    password=SENHA_FORTE,
    role=UserRole.STUDENT,
    **extra,
):
    """Cria um usuario direto pelo manager (bypassa os formularios)."""
    extra.setdefault("full_name", "Usuario de Teste")
    return User.objects.create_user(email=email, password=password, role=role, **extra)


def dados_signup(
    email="aluno@unirotas.com",
    password=SENHA_FORTE,
    confirm_password=None,
    course="Ciencia da Computacao",
    period=4,
    **extra,
):
    """Payload completo aceito pela view signup (os dois formularios juntos)."""
    dados = {
        "email": email,
        "full_name": "Aluno de Teste",
        "birth_date": "2000-05-10",
        "course": course,
        "period": period,
        "password": password,
        "confirm_password": password if confirm_password is None else confirm_password,
    }
    dados.update(extra)
    return dados


def dados_convite(
    full_name="Convidado de Teste",
    password=SENHA_FORTE,
    confirm_password=None,
    birth_date="1999-03-15",
    **extra,
):
    """Payload aceito pela tela de cadastro por convite (signup_role)."""
    dados = {
        "full_name": full_name,
        "birth_date": birth_date,
        "password": password,
        "confirm_password": password if confirm_password is None else confirm_password,
    }
    dados.update(extra)
    return dados


def token_do_link(url):
    """Extrai o token (ultimo segmento da URL) de um link de convite."""
    return [parte for parte in url.split("/") if parte][-1]


def convidar(convidador, email, role, request=None):
    """Gera um convite pelo service e devolve (link, token).

    Usar o proprio service e proposital: valida a integracao
    convite -> e-mail -> cache -> URL reversa.
    """
    link = service.generate_elevated_signup_link(
        convidador.email, email, role, request=request
    )
    assert link is not None, "o service deveria ter gerado o link de convite"
    return link, token_do_link(link)


def mensagens_de_erro_visiveis(response, form):
    """Mensagens de erro do form que realmente apareceram no HTML entregue ao usuario.

    Serve para provar que um erro de formulario nao ficou invisivel
    (o template precisa renderizar ``form.errors`` em algum lugar).
    """
    html = response.content.decode(response.charset)
    mensagens = [erro for erros in form.errors.values() for erro in erros]
    return [mensagem for mensagem in mensagens if mensagem in html]


# ---------------------------------------------------------------------------
# Bases
# ---------------------------------------------------------------------------
class CacheLimpoTestCase(TestCase):
    """Limpa o cache (locmem) antes e depois de cada teste.

    O fluxo de convites guarda estado no cache, entao um teste nao pode
    enxergar o convite criado por outro.
    """

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)


class MediaRootIsoladoMixin:
    """Aponta ``MEDIA_ROOT`` para uma pasta temporaria.

    Sem isso os uploads de teste cairiam na pasta ``media/`` do projeto.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root_temp = tempfile.mkdtemp(prefix="unirotas-test-")
        # addClassCleanup executa em ordem reversa (LIFO):
        # 1) desliga o override  2) limpa o cache do storage  3) apaga a pasta
        cls.addClassCleanup(shutil.rmtree, cls._media_root_temp, ignore_errors=True)
        cls.addClassCleanup(cls._limpar_cache_do_storage)
        cls._override_media = override_settings(MEDIA_ROOT=cls._media_root_temp)
        cls.addClassCleanup(cls._override_media.disable)
        cls._override_media.enable()
        cls._limpar_cache_do_storage()

    @classmethod
    def _limpar_cache_do_storage(cls):
        """FileSystemStorage guarda ``location`` em ``cached_property``.

        Sem limpar esse cache o override de ``MEDIA_ROOT`` nao teria efeito.
        """
        storage = getattr(default_storage, "_wrapped", default_storage)
        for atributo in ("base_location", "location", "base_url", "url"):
            storage.__dict__.pop(atributo, None)

    def arquivo_no_media(self, nome):
        return Path(settings.MEDIA_ROOT) / nome


# ---------------------------------------------------------------------------
# 1. Modelos / manager
# ---------------------------------------------------------------------------
class UserManagerTests(TestCase):
    """UserManager.create_user / create_superuser."""

    def test_create_user_normaliza_email_e_guarda_senha_com_hash(self):
        user = User.objects.create_user(
            email="  Aluno.Teste@UniRota.COM  ", password=SENHA_FORTE, full_name="Aluno"
        )

        self.assertEqual(user.email, "aluno.teste@unirota.com")
        self.assertNotEqual(user.password, SENHA_FORTE)
        self.assertTrue(user.check_password(SENHA_FORTE))

    def test_create_user_aplica_valores_padrao(self):
        user = criar_usuario(email="padrao@unirotas.com")

        self.assertEqual(user.role, UserRole.STUDENT)
        self.assertTrue(user.notifications)
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertIsNone(user.birth_date)
        self.assertFalse(user.profile_picture)
        self.assertIsNotNone(user.date_joined)

    def test_create_user_sem_email_levanta_value_error(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", password=SENHA_FORTE, full_name="Aluno")

    def test_create_user_aceita_senha_nula_e_marca_senha_inutilizavel(self):
        user = User.objects.create_user(email="sem.senha@unirotas.com", full_name="Aluno")

        self.assertFalse(user.has_usable_password())

    def test_create_superuser_marca_flags_necessarias(self):
        admin = User.objects.create_superuser(
            email="super@unirotas.com", password=SENHA_FORTE, full_name="Super"
        )

        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_active)
        self.assertTrue(admin.check_password(SENHA_FORTE))

    def test_create_superuser_exige_is_staff_e_is_superuser(self):
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email="a@unirotas.com",
                password=SENHA_FORTE,
                full_name="A",
                is_staff=False,
            )

        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email="b@unirotas.com",
                password=SENHA_FORTE,
                full_name="B",
                is_superuser=False,
            )

    def test_username_field_e_o_email(self):
        self.assertEqual(User.USERNAME_FIELD, "email")
        self.assertEqual(User.REQUIRED_FIELDS, ["full_name"])

    def test_get_by_natural_key_usa_o_email(self):
        user = criar_usuario(email="natural@unirotas.com")

        self.assertEqual(User.objects.get_by_natural_key("natural@unirotas.com"), user)


class UserModelTests(TestCase):
    """Comportamentos do modelo User usados pelos fluxos de convite/settings."""

    def test_str_retorna_email(self):
        user = criar_usuario(email="str@unirotas.com")

        self.assertEqual(str(user), "str@unirotas.com")

    def test_avatar_url_usa_imagem_padrao_sem_foto(self):
        user = criar_usuario()

        self.assertEqual(user.avatar_url, "/static/images/default-avatar.png")

    def test_avatar_url_retorna_a_foto_quando_existe(self):
        user = criar_usuario()
        user.profile_picture = "avatars/foto.png"

        self.assertIn("avatars/foto.png", user.avatar_url)

    def test_can_invite_respeita_a_hierarquia(self):
        admin = criar_usuario(email="admin@unirotas.com", role=UserRole.ADMIN)
        gerente = criar_usuario(email="gerente@unirotas.com", role=UserRole.MANAGER)
        motorista = criar_usuario(email="motorista@unirotas.com", role=UserRole.DRIVER)
        aluno = criar_usuario(email="aluno@unirotas.com", role=UserRole.STUDENT)

        self.assertTrue(admin.can_invite(UserRole.MANAGER))
        self.assertFalse(admin.can_invite(UserRole.ADMIN))
        self.assertFalse(admin.can_invite(UserRole.DRIVER))
        self.assertFalse(admin.can_invite(UserRole.STUDENT))

        self.assertTrue(gerente.can_invite(UserRole.DRIVER))
        self.assertFalse(gerente.can_invite(UserRole.MANAGER))
        self.assertFalse(gerente.can_invite(UserRole.ADMIN))

        self.assertFalse(motorista.can_invite(UserRole.STUDENT))
        self.assertFalse(aluno.can_invite(UserRole.DRIVER))

    def test_can_invite_nega_role_inexistente(self):
        admin = criar_usuario(email="admin@unirotas.com", role=UserRole.ADMIN)

        for role in (None, "", "SUPERADMIN", "manager", 0):
            with self.subTest(role=role):
                self.assertFalse(admin.can_invite(role))

    def test_can_invite_nega_usuario_inativo(self):
        admin = criar_usuario(
            email="admin@unirotas.com", role=UserRole.ADMIN, is_active=False
        )

        self.assertFalse(admin.can_invite(UserRole.MANAGER))

    def test_email_e_unico_no_banco(self):
        criar_usuario(email="unico@unirotas.com")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create(
                    email="unico@unirotas.com", password="x", full_name="Duplicado"
                )


class StudentProfileModelTests(TestCase):
    """Perfil academico do estudante."""

    def test_str_mostra_o_nome_do_aluno(self):
        user = criar_usuario(full_name="Maria Silva")
        perfil = StudentProfile.objects.create(user=user, course="Engenharia", period=3)

        self.assertEqual(str(perfil), "Estudante: Maria Silva")

    def test_um_usuario_nao_pode_ter_dois_perfis(self):
        user = criar_usuario()
        StudentProfile.objects.create(user=user, course="Direito", period=1)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StudentProfile.objects.create(user=user, course="Medicina", period=2)

    def test_apagar_usuario_apaga_o_perfil(self):
        user = criar_usuario()
        perfil = StudentProfile.objects.create(user=user, course="Direito", period=1)

        user.delete()

        self.assertFalse(StudentProfile.objects.filter(pk=perfil.pk).exists())


# ---------------------------------------------------------------------------
# 2. Formularios
# ---------------------------------------------------------------------------
class ValidacaoDeSenhaTests(TestCase):
    """Regras de senha compartilhadas pelos formularios (forms.Validation)."""

    def setUp(self):
        self.validador = Validation()

    def test_aceita_senha_com_todos_os_requisitos(self):
        for senha in ("Senha@123", "Abcdef1!", "UniRota#2026", SENHA_NOVA):
            with self.subTest(senha=senha):
                self.assertFalse(self.validador.is_password_invalid(senha, senha))

    def test_rejeita_senhas_que_nao_batem_com_a_confirmacao(self):
        self.assertTrue(self.validador.is_password_invalid("Senha@123", "Senha@124"))

    def test_rejeita_senha_sem_requisito(self):
        invalidas = {
            "curta": "Se@1",  # menos de 8 caracteres
            "sem_minuscula": "SENHA@123",
            "sem_maiuscula": "senha@123",
            "sem_numero": "Senha@abc",
            "sem_simbolo": "Senha1234",
            "vazia": "",
        }

        for caso, senha in invalidas.items():
            with self.subTest(caso=caso):
                self.assertTrue(self.validador.is_password_invalid(senha, senha))

    def test_rejeita_valores_ausentes(self):
        self.assertTrue(self.validador.is_password_invalid(None, None))
        self.assertTrue(self.validador.is_password_invalid(SENHA_FORTE, None))
        self.assertTrue(self.validador.is_password_invalid(None, SENHA_FORTE))


class UserRegistrationFormTests(TestCase):
    """Formulario de criacao de conta (usado no signup e no convite)."""

    def payload(self, **extra):
        dados = {
            "email": "novo@unirotas.com",
            "full_name": "Novo Usuario",
            "birth_date": "2000-05-10",
            "password": SENHA_FORTE,
            "confirm_password": SENHA_FORTE,
        }
        dados.update(extra)
        return dados

    def test_form_valido_salva_usuario_com_senha_hasheada(self):
        form = UserRegistrationForm(data=self.payload())
        self.assertTrue(form.is_valid(), form.errors)

        user = form.save()

        self.assertEqual(user.email, "novo@unirotas.com")
        self.assertEqual(user.full_name, "Novo Usuario")
        self.assertEqual(user.birth_date, date(2000, 5, 10))
        self.assertTrue(user.check_password(SENHA_FORTE))
        self.assertEqual(user.role, UserRole.STUDENT)

    def test_form_normaliza_email_em_caixa_alta(self):
        form = UserRegistrationForm(data=self.payload(email="  NOVO.USUARIO@UniRota.COM "))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["email"], "novo.usuario@unirota.com")
        self.assertEqual(form.save().email, "novo.usuario@unirota.com")

    def test_form_rejeita_email_ja_cadastrado(self):
        criar_usuario(email="novo@unirotas.com")
        form = UserRegistrationForm(data=self.payload())

        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_form_rejeita_senhas_divergentes(self):
        form = UserRegistrationForm(data=self.payload(confirm_password=SENHA_NOVA))

        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)

    def test_form_rejeita_senha_fraca(self):
        form = UserRegistrationForm(data=self.payload(password="123", confirm_password="123"))

        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)

    def test_form_rejeita_email_invalido(self):
        form = UserRegistrationForm(data=self.payload(email="nao-e-email"))

        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_form_rejeita_nome_completo_em_branco(self):
        form = UserRegistrationForm(data=self.payload(full_name=""))

        self.assertFalse(form.is_valid())
        self.assertIn("full_name", form.errors)

    def test_data_de_nascimento_e_opcional(self):
        form = UserRegistrationForm(data=self.payload(birth_date=""))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["birth_date"])

    def test_data_de_nascimento_aceita_formato_brasileiro(self):
        form = UserRegistrationForm(data=self.payload(birth_date="10/05/2000"))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["birth_date"], date(2000, 5, 10))

    def test_form_nao_aceita_role_enviada_pelo_cliente(self):
        """role nao esta em Meta.fields, entao o POST nao deve influenciar o cargo."""
        form = UserRegistrationForm(data=self.payload(role=UserRole.ADMIN))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().role, UserRole.STUDENT)


class StudentProfileFormTests(TestCase):
    """Formulario dos dados academicos."""

    def test_form_valido(self):
        form = StudentProfileForm(data={"course": "Engenharia", "period": 5})

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["period"], 5)

    def test_curso_em_branco_e_invalido(self):
        form = StudentProfileForm(data={"course": "", "period": 5})

        self.assertFalse(form.is_valid())
        self.assertIn("course", form.errors)

    def test_periodo_com_texto_e_invalido(self):
        form = StudentProfileForm(data={"course": "Engenharia", "period": "abc"})

        self.assertFalse(form.is_valid())
        self.assertIn("period", form.errors)

    def test_periodo_negativo_e_invalido(self):
        form = StudentProfileForm(data={"course": "Engenharia", "period": -1})

        self.assertFalse(form.is_valid())
        self.assertIn("period", form.errors)

    def test_periodo_em_branco_e_invalido(self):
        form = StudentProfileForm(data={"course": "Engenharia", "period": ""})

        self.assertFalse(form.is_valid())
        self.assertIn("period", form.errors)


class LoginFormTests(TestCase):
    """Formulario de login."""

    def test_form_valido_e_normaliza_email(self):
        form = LoginForm(data={"email": " Aluno@UniRota.COM ", "password": SENHA_FORTE})

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["email"], "aluno@unirota.com")

    def test_email_invalido(self):
        form = LoginForm(data={"email": "nao-e-email", "password": SENHA_FORTE})

        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_senha_vazia_e_invalida(self):
        form = LoginForm(data={"email": "aluno@unirotas.com", "password": ""})

        self.assertFalse(form.is_valid())
        self.assertIn("password", form.errors)


class ChangePasswordFormTests(TestCase):
    """Formulario de troca de senha (senha atual + nova + confirmacao)."""
    def setUp(self):
        # 1. Cria o usuário aqui para que self.user exista!
        self.user = User.objects.create_user(
            full_name="teste", 
            email="teste@email.com", 
            password="senha-Antiga-123"
        )
    
    def payload(self, **extra):
        dados = {
            "password": SENHA_FORTE,
            "new_password1": SENHA_NOVA,
            "new_password2": SENHA_NOVA,
        }
        dados.update(extra)
        return dados

    def test_form_valido(self):
        form = ChangePassword(data=self.payload(), user=self.user)

        self.assertTrue(form.is_valid(), form.errors)

    def test_novas_senhas_divergentes_sao_invalidas(self):
        form = ChangePassword(data=self.payload(new_password2="Outra@999"), user=self.user)

        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)

    def test_nova_senha_fraca_e_invalida(self):
        form = ChangePassword(data=self.payload(new_password1="123", new_password2="123"), user=self.user)

        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)

    def test_form_nao_valida_a_senha_atual(self):
        """O form apenas recebe a senha atual; quem confere e a view."""
        form = ChangePassword(data=self.payload(password="qualquer-coisa"), user=self.user)

        self.assertTrue(form.is_valid(), form.errors)


# ---------------------------------------------------------------------------
# 3. Fluxo publico de cadastro (signup)
# ---------------------------------------------------------------------------
class SignupViewTests(CacheLimpoTestCase):
    """Fluxo completo de cadastro do estudante."""

    def setUp(self):
        super().setUp()
        self.url = reverse("authentication:signup")

    def test_get_renderiza_o_formulario(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "signup.html")
        self.assertIsInstance(response.context["form_account"], UserRegistrationForm)
        self.assertIsInstance(response.context["form_student"], StudentProfileForm)

    def test_post_valido_cria_conta_e_perfil_e_redireciona_para_login(self):
        response = self.client.post(
            self.url, dados_signup(email="aluno.novo@unirotas.com"), follow=False
        )

        self.assertRedirects(response, reverse("authentication:login"))

        user = User.objects.get(email="aluno.novo@unirotas.com")
        self.assertEqual(user.full_name, "Aluno de Teste")
        self.assertEqual(user.role, UserRole.STUDENT)
        self.assertEqual(user.birth_date, date(2000, 5, 10))
        self.assertTrue(user.check_password(SENHA_FORTE))
        self.assertNotEqual(user.password, SENHA_FORTE)

        perfil = user.student_profile
        self.assertEqual(perfil.course, "Ciencia da Computacao")
        self.assertEqual(perfil.period, 4)

    def test_post_valido_nao_autentica_o_usuario(self):
        self.client.post(self.url, dados_signup())

        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_aluno_recem_cadastrado_consegue_logar(self):
        self.client.post(self.url, dados_signup(email="aluno.login@unirotas.com"))

        response = self.client.post(
            reverse("authentication:login"),
            {"email": "aluno.login@unirotas.com", "password": SENHA_FORTE},
        )

        self.assertRedirects(response, reverse("authentication:settings"))

    def test_post_normaliza_email_em_caixa_alta(self):
        self.client.post(self.url, dados_signup(email="ALUNO.CAPS@UniRota.COM"))

        self.assertTrue(User.objects.filter(email="aluno.caps@unirota.com").exists())

    def test_post_sem_data_de_nascimento_funciona(self):
        self.client.post(self.url, dados_signup(birth_date=""))

        user = User.objects.get(email="aluno@unirotas.com")
        self.assertIsNone(user.birth_date)

    def test_post_com_email_ja_cadastrado_nao_cria_nada(self):
        criar_usuario(email="aluno@unirotas.com")

        response = self.client.post(self.url, dados_signup())

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "signup.html")
        self.assertFalse(response.context["form_account"].is_valid())
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(StudentProfile.objects.count(), 0)

    def test_post_com_senhas_divergentes_nao_cria_usuario(self):
        response = self.client.post(self.url, dados_signup(confirm_password="Outra@123"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_post_com_senha_fraca_nao_cria_usuario(self):
        response = self.client.post(
            self.url, dados_signup(password="123", confirm_password="123")
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_post_com_email_invalido_nao_cria_usuario(self):
        response = self.client.post(self.url, dados_signup(email="sem-arroba"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_post_com_dados_academicos_invalidos_nao_cria_nem_usuario_nem_perfil(self):
        for curso, periodo in (("", 4), ("Ciencia da Computacao", ""), ("Ciencia", "abc")):
            with self.subTest(curso=curso, periodo=periodo):
                response = self.client.post(
                    self.url, dados_signup(course=curso, period=periodo)
                )
                self.assertEqual(response.status_code, 200)
                self.assertFalse(User.objects.exists())
                self.assertFalse(StudentProfile.objects.exists())

    def test_post_ignora_role_enviada_no_payload(self):
        """Escalonamento de cargo pelo cadastro publico nao pode funcionar."""
        response = self.client.post(
            self.url,
            dados_signup(role=UserRole.ADMIN, is_staff=True, is_superuser=True),
        )

        self.assertRedirects(response, reverse("authentication:login"))
        user = User.objects.get(email="aluno@unirotas.com")
        self.assertEqual(user.role, UserRole.STUDENT)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_erro_no_perfil_academico_faz_rollback_da_conta(self):
        """transaction.atomic precisa desfazer o usuario se o perfil falhar."""
        with patch.object(
            StudentProfile.objects, "create", side_effect=Exception("falha simulada")
        ):
            response = self.client.post(
                self.url, dados_signup(email="rollback@unirotas.com")
            )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "signup.html")
        self.assertIn("erro", response.context["error"].lower())
        self.assertFalse(User.objects.filter(email="rollback@unirotas.com").exists())


# ---------------------------------------------------------------------------
# 4. Login e logout
# ---------------------------------------------------------------------------
class LoginViewTests(TestCase):
    """Fluxo de autenticacao."""

    def setUp(self):
        self.url = reverse("authentication:login")
        self.user = criar_usuario(email="aluno@unirotas.com", password=SENHA_FORTE)

    def test_get_renderiza_o_formulario(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "login.html")
        self.assertIsInstance(response.context["form_login"], LoginForm)

    def test_post_com_credenciais_validas_autentica_e_redireciona(self):
        response = self.client.post(
            self.url, {"email": "aluno@unirotas.com", "password": SENHA_FORTE}
        )

        self.assertRedirects(response, reverse("authentication:settings"))
        self.assertEqual(int(self.client.session[SESSION_KEY]), self.user.pk)

        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.last_login)

    def test_post_aceita_email_em_caixa_alta(self):
        response = self.client.post(
            self.url, {"email": "ALUNO@UNIROTAS.COM", "password": SENHA_FORTE}
        )

        self.assertRedirects(response, reverse("authentication:settings"))

    def test_login_rotaciona_a_chave_de_sessao(self):
        """Protecao contra session fixation."""
        self.client.session["marcador"] = "visitante"
        self.client.session.save()
        chave_antes = self.client.session.session_key

        self.client.post(
            self.url, {"email": "aluno@unirotas.com", "password": SENHA_FORTE}
        )

        self.assertNotEqual(self.client.session.session_key, chave_antes)

    def test_post_com_senha_errada_nao_autentica(self):
        response = self.client.post(
            self.url, {"email": "aluno@unirotas.com", "password": "Errada@123"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertTrue(response.context["form_login"].errors)

    def test_post_com_email_inexistente_nao_autentica(self):
        response = self.client.post(
            self.url, {"email": "ninguem@unirotas.com", "password": SENHA_FORTE}
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertTrue(response.context["form_login"].errors)

    def test_post_nao_autentica_usuario_inativo(self):
        self.user.is_active = False
        self.user.save()

        response = self.client.post(
            self.url, {"email": "aluno@unirotas.com", "password": SENHA_FORTE}
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_post_nao_autentica_com_senha_vazia(self):
        response = self.client.post(
            self.url, {"email": "aluno@unirotas.com", "password": ""}
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_mensagem_de_erro_nao_revela_qual_campo_esta_errado(self):
        """Evita enumeracao de contas: mesma mensagem para senha e email errados."""
        resposta_senha = self.client.post(
            self.url, {"email": "aluno@unirotas.com", "password": "Errada@123"}
        )
        erros_senha = resposta_senha.context["form_login"].errors["__all__"]

        resposta_email = self.client.post(
            self.url, {"email": "ninguem@unirotas.com", "password": SENHA_FORTE}
        )
        erros_email = resposta_email.context["form_login"].errors["__all__"]

        self.assertEqual(list(erros_senha), list(erros_email))
        self.assertEqual(
            [str(erro) for erro in erros_senha], ["E-mail ou senha inválidos."]
        )

    def test_usuario_logado_que_volta_no_login_continua_autenticado(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIn(SESSION_KEY, self.client.session)


class LogoutViewTests(TestCase):
    """Logout implementado pelo LogoutView do Django (apenas POST)."""

    def setUp(self):
        self.usuario = criar_usuario()
        self.client.force_login(self.usuario)

    def test_post_desloga_e_redireciona_para_login(self):
        response = self.client.post(reverse("authentication:logout"))

        self.assertRedirects(response, reverse("authentication:login"))
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_get_nao_desloga(self):
        """Django 5+ exige POST: GET nao pode ser usado para deslogar."""
        response = self.client.get(reverse("authentication:logout"))

        self.assertEqual(response.status_code, 405)
        self.assertIn(SESSION_KEY, self.client.session)


# ---------------------------------------------------------------------------
# 5. Convites para cargos elevados - service
# ---------------------------------------------------------------------------
class ConviteServiceTests(CacheLimpoTestCase):
    """service.generate/abort/recreate_elevated_signup_link e envio de e-mail."""

    def setUp(self):
        super().setUp()
        self.admin = criar_usuario(email="admin@unirotas.com", role=UserRole.ADMIN)
        self.gerente = criar_usuario(email="gerente@unirotas.com", role=UserRole.MANAGER)
        self.email_convidado = "novo.gestor@unirotas.com"

    def chave_convite(self, token):
        return f"invitation_{token}"

    def chave_ponteiro(self, email_convidador, email_convidado):
        return f"invitation_pointer_{email_convidador}_{email_convidado}"

    def test_gera_link_com_token_assinado_e_url_reversa(self):
        link, token = convidar(self.admin, self.email_convidado, UserRole.MANAGER)

        self.assertEqual(
            link, reverse("authentication:elevated_signup", kwargs={"token": token})
        )
        self.assertEqual(Signer().unsign(token), self.email_convidado)

    def test_gera_link_absoluto_quando_recebe_request(self):
        request = RequestFactory().get("/")

        link, token = convidar(
            self.admin, self.email_convidado, UserRole.MANAGER, request=request
        )

        self.assertTrue(link.startswith("http://testserver/auth/elevated/signup/"))
        self.assertIn(token, link)

    def test_envia_email_de_convite_para_o_email_convidado(self):
        link, token = convidar(self.admin, self.email_convidado, UserRole.MANAGER)

        self.assertEqual(len(mail.outbox), 1)
        mensagem = mail.outbox[0]
        self.assertEqual(mensagem.to, [self.email_convidado])
        self.assertEqual(mensagem.from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertTrue(mensagem.subject)
        self.assertIn(link, mensagem.body)

    def test_guarda_convite_e_ponteiro_no_cache(self):
        _, token = convidar(self.admin, self.email_convidado, UserRole.MANAGER)

        convite = cache.get(self.chave_convite(token))
        self.assertEqual(convite["email"], self.email_convidado)
        self.assertEqual(convite["role"], UserRole.MANAGER)
        self.assertEqual(convite["higher_role_email"], self.admin.email)
        self.assertIsNotNone(
            cache.get(self.chave_ponteiro(self.admin.email, self.email_convidado))
        )

    def test_normaliza_emails_com_espacos_e_caixa_alta(self):
        link = service.generate_elevated_signup_link(
            "  ADMIN@UniRotaS.COM ", "  Novo.Gestor@UniRotaS.COM  ", UserRole.MANAGER
        )

        self.assertIsNotNone(link)
        token = token_do_link(link)
        self.assertEqual(Signer().unsign(token), "novo.gestor@unirotas.com")
        self.assertEqual(mail.outbox[0].to, ["novo.gestor@unirotas.com"])

    def test_convidador_inexistente_nao_gera_link(self):
        link = service.generate_elevated_signup_link(
            "fantasma@unirotas.com", self.email_convidado, UserRole.MANAGER
        )

        self.assertIsNone(link)
        self.assertEqual(len(mail.outbox), 0)

    def test_admin_nao_pode_convidar_motorista_diretamente(self):
        link = service.generate_elevated_signup_link(
            self.admin.email, self.email_convidado, UserRole.DRIVER
        )

        self.assertIsNone(link)
        self.assertEqual(len(mail.outbox), 0)
        token = Signer().sign(self.email_convidado)
        self.assertIsNone(cache.get(self.chave_convite(token)))

    def test_gerente_nao_pode_convidar_gerente(self):
        link = service.generate_elevated_signup_link(
            self.gerente.email, self.email_convidado, UserRole.MANAGER
        )

        self.assertIsNone(link)
        self.assertEqual(len(mail.outbox), 0)


    def test_cargos_invalidos_nao_geram_link(self):
        for role in (None, "", "ADMIN", "STUDENT", "SUPERADMIN", UserRole.STUDENT):
            with self.subTest(role=role):
                self.assertIsNone(
                    service.generate_elevated_signup_link(
                        self.admin.email, self.email_convidado, role
                    )
                )

        self.assertEqual(len(mail.outbox), 0)

    def test_convidador_inativo_nao_gera_link(self):
        self.admin.is_active = False
        self.admin.save()

        link = service.generate_elevated_signup_link(
            self.admin.email, self.email_convidado, UserRole.MANAGER
        )

        self.assertIsNone(link)
        self.assertEqual(len(mail.outbox), 0)

    def test_falha_no_envio_do_email_nao_deixa_convite_no_cache(self):
        """Fallback do service: sem e-mail enviado nao existe convite valido."""
        with patch("authentication.service.send_mail", return_value=0):
            link = service.generate_elevated_signup_link(
                self.admin.email, self.email_convidado, UserRole.MANAGER
            )

        self.assertIsNone(link)
        token = Signer().sign(self.email_convidado)
        self.assertIsNone(cache.get(self.chave_convite(token)))

    def test_abort_remove_convite_e_ponteiro(self):
        _, token = convidar(self.admin, self.email_convidado, UserRole.MANAGER)

        service.abort_elevated_signup_link(self.admin.email, self.email_convidado)

        self.assertIsNone(cache.get(self.chave_convite(token)))
        self.assertIsNone(
            cache.get(self.chave_ponteiro(self.admin.email, self.email_convidado))
        )

    def test_recreate_envia_novo_email_e_deixa_convite_valido(self):
        convidar(self.admin, self.email_convidado, UserRole.MANAGER)

        link = service.recreate_elevated_signup_link(
            self.admin.email, self.email_convidado, UserRole.MANAGER
        )

        self.assertEqual(len(mail.outbox), 2)
        token = token_do_link(link)
        self.assertIsNotNone(cache.get(self.chave_convite(token)))

    def test_recreate_exige_que_o_convidador_ainda_possa_convidar(self):
        convidar(self.admin, self.email_convidado, UserRole.MANAGER)
        self.admin.role = UserRole.STUDENT
        self.admin.save()

        link = service.recreate_elevated_signup_link(
            self.admin.email, self.email_convidado, UserRole.MANAGER
        )

        self.assertIsNone(link)
        self.assertEqual(len(mail.outbox), 1)  # nao enviou o segundo e-mail


# ---------------------------------------------------------------------------
# 6. Convites - fluxo integrado (criar convite, consumir e validar)
# ---------------------------------------------------------------------------
class ConviteFluxoIntegracaoTests(CacheLimpoTestCase):
    """Cria o convite pelo service, consome a URL e confere o resultado."""

    def setUp(self):
        super().setUp()
        self.admin = criar_usuario(email="admin@unirotas.com", role=UserRole.ADMIN)
        self.gerente = criar_usuario(email="gerente@unirotas.com", role=UserRole.MANAGER)
        self.email_convidado = "novo.motorista@unirotas.com"

    def abrir(self, link):
        return self.client.get(link)

    def consumir(self, link, **extra):
        """Faz o POST de cadastro na URL do convite."""
        return self.client.post(link, dados_convite(**extra))

    def test_fluxo_admin_convida_gerente_ate_o_convite_ser_consumido(self):
        link, token = convidar(self.admin, "novo.gestor@unirotas.com", UserRole.MANAGER)

        # 1) o convidado abre o link
        resposta_get = self.abrir(link)
        self.assertEqual(resposta_get.status_code, 200)
        self.assertTemplateUsed(resposta_get, "signup_role.html")
        self.assertIsInstance(
            resposta_get.context["form_account"], UserRegistrationForm
        )

        # 2) o convite esta guardado no cache (ainda nao consumido)
        self.assertIsNotNone(cache.get(f"invitation_{token}"))

        # 3) o convidado conclui o cadastro
        resposta_post = self.consumir(link, full_name="Novo Gestor")
        self.assertRedirects(resposta_post, reverse("authentication:login"))

        # 4) a conta existe com o cargo do convite
        user = User.objects.get(email="novo.gestor@unirotas.com")
        self.assertEqual(user.role, UserRole.MANAGER)
        self.assertEqual(user.full_name, "Novo Gestor")
        self.assertEqual(user.birth_date, date(1999, 3, 15))
        self.assertTrue(user.check_password(SENHA_FORTE))
        self.assertFalse(StudentProfile.objects.filter(user=user).exists())

        # 5) o convite foi realmente consumido
        self.assertIsNone(cache.get(f"invitation_{token}"))
        self.assertIsNone(
            cache.get(f"invitation_pointer_{self.admin.email}_novo.gestor@unirotas.com")
        )

        # 6) reutilizar o link nao funciona mais
        resposta_reuso = self.abrir(link)
        self.assertEqual(resposta_reuso.status_code, 200)
        self.assertTemplateUsed(resposta_reuso, "erro_convite.html")
        self.assertContains(resposta_reuso, "expirou")
        self.assertEqual(
            User.objects.filter(email="novo.gestor@unirotas.com").count(), 1
        )

    def test_fluxo_gerente_convida_motorista_e_consegue_logar(self):
        link, token = convidar(self.gerente, self.email_convidado, UserRole.DRIVER)

        self.assertRedirects(
            self.consumir(link, full_name="Motorista Novo"),
            reverse("authentication:login"),
        )

        user = User.objects.get(email=self.email_convidado)
        self.assertEqual(user.role, UserRole.DRIVER)
        self.assertIsNone(cache.get(f"invitation_{token}"))

        resposta_login = self.client.post(
            reverse("authentication:login"),
            {"email": self.email_convidado, "password": SENHA_FORTE},
        )
        self.assertRedirects(resposta_login, reverse("authentication:settings"))

    def test_post_repetido_no_mesmo_link_nao_cria_duas_contas(self):
        link, _ = convidar(self.admin, self.email_convidado, UserRole.MANAGER)

        self.consumir(link)
        resposta = self.consumir(link)

        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "erro_convite.html")
        self.assertEqual(User.objects.filter(email=self.email_convidado).count(), 1)

    def test_cargo_do_convite_nao_pode_ser_trocado_no_payload(self):
        link, _ = convidar(self.admin, self.email_convidado, UserRole.MANAGER)

        self.consumir(link, role=UserRole.ADMIN, is_staff=True, is_superuser=True)

        user = User.objects.get(email=self.email_convidado)
        self.assertEqual(user.role, UserRole.MANAGER)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_email_do_payload_e_ignorado_o_token_manda(self):
        link, _ = convidar(self.admin, self.email_convidado, UserRole.MANAGER)

        resposta = self.client.post(link, dados_convite(email="invasor@unirotas.com"))

        self.assertRedirects(resposta, reverse("authentication:login"))
        self.assertTrue(User.objects.filter(email=self.email_convidado).exists())
        self.assertFalse(User.objects.filter(email="invasor@unirotas.com").exists())


    def test_token_adulterado_renderiza_pagina_de_erro(self):
        link, token = convidar(self.admin, self.email_convidado, UserRole.MANAGER)
        # troca a assinatura do token mantendo a URL valida (o token e o ultimo
        # segmento da URL, antes da barra final)
        link_adulterado = link[:-1] + "assinaturafalsa/"

        resposta = self.abrir(link_adulterado)

        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "erro_convite.html")
        self.assertContains(resposta, "inválido")
        self.assertFalse(User.objects.filter(email=self.email_convidado).exists())

    def test_token_valido_sem_convite_no_cache_nao_cadastra(self):
        token = Signer().sign(self.email_convidado)
        link = reverse("authentication:elevated_signup", kwargs={"token": token})

        resposta = self.abrir(link)

        self.assertTemplateUsed(resposta, "erro_convite.html")
        self.assertContains(resposta, "expirou")

    def test_convite_expirado_no_cache_deixa_de_funcionar(self):
        link, token = convidar(self.admin, self.email_convidado, UserRole.MANAGER)
        cache.delete(f"invitation_{token}")  # simula o TTL de 24h estourando

        resposta = self.consumir(link)

        self.assertTemplateUsed(resposta, "erro_convite.html")
        self.assertFalse(User.objects.filter(email=self.email_convidado).exists())

    def test_convite_de_convidador_desativado_deixa_de_funcionar(self):
        link, _ = convidar(self.admin, self.email_convidado, UserRole.MANAGER)

        self.admin.is_active = False
        self.admin.save()

        resposta = self.abrir(link)

        self.assertTemplateUsed(resposta, "erro_convite.html")
        self.assertContains(resposta, "não é válido")

    def test_convite_de_convidador_rebaixado_deixa_de_funcionar(self):
        link, _ = convidar(self.admin, self.email_convidado, UserRole.MANAGER)

        self.admin.role = UserRole.STUDENT
        self.admin.save()

        resposta = self.abrir(link)

        self.assertTemplateUsed(resposta, "erro_convite.html")
        self.assertContains(resposta, "não é válido")

    def test_convite_abortado_deixa_de_funcionar(self):
        link, _ = convidar(self.admin, self.email_convidado, UserRole.MANAGER)

        service.abort_elevated_signup_link(self.admin.email, self.email_convidado)

        resposta = self.abrir(link)

        self.assertTemplateUsed(resposta, "erro_convite.html")
        self.assertContains(resposta, "expirou")

    def test_convite_recriado_continua_sendo_consumivel(self):
        convidar(self.admin, self.email_convidado, UserRole.MANAGER)
        novo_link = service.recreate_elevated_signup_link(
            self.admin.email, self.email_convidado, UserRole.MANAGER
        )

        resposta = self.consumir(novo_link)

        self.assertRedirects(resposta, reverse("authentication:login"))
        self.assertEqual(
            User.objects.get(email=self.email_convidado).role, UserRole.MANAGER
        )

    def test_post_invalido_no_convite_nao_consome_o_convite(self):
        link, token = convidar(self.admin, self.email_convidado, UserRole.MANAGER)

        resposta = self.consumir(link, confirm_password="Outra@123")

        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "signup_role.html")
        self.assertFalse(User.objects.filter(email=self.email_convidado).exists())
        # o convite continua valido para a proxima tentativa
        self.assertIsNotNone(cache.get(f"invitation_{token}"))

        self.assertRedirects(self.consumir(link), reverse("authentication:login"))

    def test_email_do_convite_e_enviado_antes_de_consumir(self):
        convidar(self.gerente, self.email_convidado, UserRole.DRIVER)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.email_convidado])
        self.assertIn("/auth/elevated/signup/", mail.outbox[0].body)


# ---------------------------------------------------------------------------
# 7. Area logada
# ---------------------------------------------------------------------------
class ViewsProtegidasTests(TestCase):
    """Todas as telas da area logada exigem autenticacao."""

    def test_views_protegidas_redirecionam_visitante_para_o_login(self):
        rotas = [
            "authentication:settings",
            "authentication:my_information",
            "authentication:change_password",
            "authentication:change_avatar",
            "authentication:toggle_notification",
        ]

        for rota in rotas:
            with self.subTest(rota=rota):
                destino = reverse(rota)
                response = self.client.get(destino)

                self.assertEqual(response.status_code, 302)
                self.assertEqual(
                    response.url, f"{reverse('authentication:login')}?next={destino}"
                )


class SettingsViewTests(TestCase):
    """Tela de configuracoes/perfil."""

    def setUp(self):
        self.user = criar_usuario(
            email="aluno@unirotas.com", full_name="Aluno Teste", notifications=True
        )
        self.client.force_login(self.user)
        self.url = reverse("authentication:settings")

    def test_renderiza_os_dados_do_usuario(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "settings.html")
        self.assertContains(response, "Aluno Teste")
        self.assertContains(response, "aluno@unirotas.com")
        self.assertEqual(response.context["full_name"], "Aluno Teste")
        self.assertEqual(response.context["email"], "aluno@unirotas.com")
        self.assertTrue(response.context["notifications"])

    def test_mostra_avatar_padrao_quando_nao_tem_foto(self):
        response = self.client.get(self.url)

        self.assertContains(response, "images/settings/base_profile.png")

    def test_mostra_a_foto_do_usuario_quando_existe(self):
        self.user.profile_picture = "avatars/foto.png"
        self.user.save()

        response = self.client.get(self.url)

        self.assertContains(response, settings.MEDIA_URL + "avatars/foto.png")

    def test_botao_de_notificacao_reflete_o_estado(self):
        response_ligado = self.client.get(self.url)
        self.assertContains(response_ligado, "toggle-switch active")

        self.user.notifications = False
        self.user.save()
        response_desligado = self.client.get(self.url)
        self.assertNotContains(response_desligado, "toggle-switch active")


class ToggleNotificationTests(TestCase):
    """View que liga/desliga a notificacao push."""

    def setUp(self):
        self.user = criar_usuario(notifications=True)
        self.client.force_login(self.user)
        self.url = reverse("authentication:toggle_notification")

    def test_post_alterna_o_valor_no_banco(self):
        response = self.client.post(self.url)

        self.assertRedirects(response, reverse("authentication:settings"))
        self.user.refresh_from_db()
        self.assertFalse(self.user.notifications)

        self.client.post(self.url)
        self.user.refresh_from_db()
        self.assertTrue(self.user.notifications)

    def test_get_nao_alterna_o_valor(self):
        self.client.get(self.url)

        self.user.refresh_from_db()
        self.assertTrue(self.user.notifications)

    def test_post_de_visitante_nao_alterna_nada(self):
        self.client.logout()

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.notifications)


class MyInformationViewTests(TestCase):
    """Tela 'Meus dados'."""

    def setUp(self):
        self.user = criar_usuario(
            email="aluno@unirotas.com",
            full_name="Aluno Teste",
            birth_date=date(2000, 5, 10),
        )
        self.client.force_login(self.user)
        self.url = reverse("authentication:my_information")

    def test_renderiza_dados_pessoais(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "my_information.html")
        self.assertEqual(response.context["full_name"], "Aluno Teste")
        self.assertEqual(response.context["email"], "aluno@unirotas.com")
        self.assertEqual(response.context["birth_date"], date(2000, 5, 10))
        self.assertContains(response, "10/05/2000")

    def test_mostra_texto_padrao_sem_data_de_nascimento(self):
        self.user.birth_date = None
        self.user.save()

        response = self.client.get(self.url)

        self.assertContains(response, "Não informada")

import base64

class ChangeAvatarTests(MediaRootIsoladoMixin, TestCase):
    """Upload da foto de perfil."""

    def setUp(self):
        self.user = criar_usuario(email="aluno@unirotas.com")
        self.client.force_login(self.user)
        self.url = reverse("authentication:change_avatar")

    def arquivo(self, nome="foto.png", conteudo=b"conteudo-de-teste", tipo="image/png"):
        tiny_png_bytes = base64.b64decode(
        b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        )
        return SimpleUploadedFile(nome, tiny_png_bytes, content_type=tipo)

    def test_post_salva_a_foto_e_redireciona(self):
        response = self.client.post(
            self.url, {"profile_picture": self.arquivo()}, follow=False
        )

        self.assertRedirects(response, reverse("authentication:my_information"))

        self.user.refresh_from_db()
        self.assertTrue(self.user.profile_picture.name.startswith("avatars/"))
        self.assertTrue(self.user.profile_picture.name.endswith("foto.png"))
        self.assertTrue(self.arquivo_no_media(self.user.profile_picture.name).exists())
        self.assertTrue(
            self.user.profile_picture.storage.exists(self.user.profile_picture.name)
        )

    # -- 1. upload de avatar sem nenhuma validacao ---------------------------
        def test_avatar_nao_deve_aceitar_arquivo_que_nao_e_imagem(self):
            """URGENTE - upload de arquivo arbitrario.
    
            `change_avatar` grava `request.FILES.get('profile_picture')` direto no
            model, sem passar por um Form/ImageField. Resultado: qualquer arquivo
            (.html, .svg com script, executavel) e aceito e servido em /media/.
            Esperado: recusar e nao salvar.
            """
            usuario = criar_usuario(email="upload@unirotas.com")
            self.client.force_login(usuario)
    
            self.client.post(
                reverse("authentication:change_avatar"),
                {
                    "profile_picture": SimpleUploadedFile(
                        "malicioso.html",
                        b"<script>alert('xss')</script>",
                        content_type="text/html",
                    )
                },
            )
    
            usuario.refresh_from_db()
            self.assertFalse(
                usuario.profile_picture,
                "A view aceitou um arquivo .html como foto de perfil "
                "(upload arbitrario e possivel stored XSS servido em /media/).",
            )

    def test_avatar_nao_deve_aceitar_arquivo_gigante(self):
            """URGENTE - upload sem limite de tamanho (risco de encher o disco)."""
            usuario = criar_usuario(email="upload.grande@unirotas.com")
            self.client.force_login(usuario)
            conteudo = b"0" * (5 * 1024 * 1024)  # 5 MB
    
            self.client.post(
                reverse("authentication:change_avatar"),
                {
                    "profile_picture": SimpleUploadedFile(
                        "grande.png", conteudo, content_type="image/png"
                    )
                },
            )
    
            usuario.refresh_from_db()
            self.assertFalse(
                usuario.profile_picture,
                "A view aceitou uma foto de 5MB: falta limite de tamanho no upload.",
            )
    
    def test_post_substitui_a_foto_anterior(self):
        self.client.post(self.url, {"profile_picture": self.arquivo("primeira.png")})
        self.client.post(self.url, {"profile_picture": self.arquivo("segunda.png")})

        self.user.refresh_from_db()
        self.assertTrue(self.user.profile_picture.name.endswith("segunda.png"))

    def test_post_sem_arquivo_nao_altera_a_foto(self):
        response = self.client.post(self.url, {})

        self.assertRedirects(response, reverse("authentication:my_information"))
        self.user.refresh_from_db()
        self.assertFalse(self.user.profile_picture)

    def test_get_nao_altera_a_foto(self):
        self.client.get(self.url)

        self.user.refresh_from_db()
        self.assertFalse(self.user.profile_picture)

    def test_visitante_nao_consegue_enviar_arquivo(self):
        self.client.logout()

        response = self.client.post(
            self.url, {"profile_picture": self.arquivo("arquivo-do-visitante.png")}
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("authentication:login"), response.url)
        self.user.refresh_from_db()
        self.assertFalse(self.user.profile_picture)
        self.assertFalse(
            self.arquivo_no_media("avatars/arquivo-do-visitante.png").exists()
        )


class ChangePasswordViewTests(TestCase):
    """Troca de senha dentro da area logada."""

    def setUp(self):
        self.user = criar_usuario(email="aluno@unirotas.com", password=SENHA_FORTE)
        self.client.force_login(self.user)
        self.url = reverse("authentication:change_password")

    def payload(self, **extra):
        dados = {
            "password": SENHA_FORTE,
            "new_password1": SENHA_NOVA,
            "new_password2": SENHA_NOVA,
        }
        dados.update(extra)
        return dados

    def test_get_renderiza_o_formulario(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "change_password.html")
        self.assertIsInstance(response.context["form"], ChangePassword)

    def test_post_valido_troca_a_senha_e_mantem_a_sessao(self):
        response = self.client.post(self.url, self.payload())

        self.assertRedirects(response, reverse("authentication:my_information"))

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(SENHA_NOVA))
        self.assertFalse(self.user.check_password(SENHA_FORTE))
        self.assertIn(SESSION_KEY, self.client.session)

    def test_login_com_a_senha_nova_funciona_e_com_a_antiga_nao(self):
        self.client.post(self.url, self.payload())
        self.client.logout()

        antiga = self.client.post(
            reverse("authentication:login"),
            {"email": "aluno@unirotas.com", "password": SENHA_FORTE},
        )
        self.assertEqual(antiga.status_code, 200)
        self.assertNotIn(SESSION_KEY, self.client.session)

        nova = self.client.post(
            reverse("authentication:login"),
            {"email": "aluno@unirotas.com", "password": SENHA_NOVA},
        )
        self.assertRedirects(nova, reverse("authentication:settings"))

    def test_senha_atual_errada_nao_troca_a_senha(self):
        response = self.client.post(self.url, self.payload(password="Errada@123"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "change_password.html")
        self.assertIn("não foi possivel", response.context["error"])

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(SENHA_FORTE))

    def test_senhas_novas_divergentes_nao_trocam_a_senha(self):
        response = self.client.post(
            self.url, self.payload(new_password2="Outra@999")
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(SENHA_FORTE))

    def test_nova_senha_fraca_nao_troca_a_senha(self):
        response = self.client.post(
            self.url, self.payload(new_password1="123", new_password2="123")
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(SENHA_FORTE))

    def test_senha_atual_em_branco_nao_troca_a_senha(self):
        response = self.client.post(self.url, self.payload(password=""))

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(SENHA_FORTE))

    def test_post_incompleto_nao_troca_a_senha(self):
        response = self.client.post(self.url, {})

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(SENHA_FORTE))


# ---------------------------------------------------------------------------
# 8. Reset de senha por e-mail (fluxo completo)
# ---------------------------------------------------------------------------
class PasswordResetFlowTests(TestCase):
    """Usa o link que sai em mail.outbox para redefinir a senha de verdade."""

    def setUp(self):
        self.email = "aluno@unirotas.com"
        self.user = criar_usuario(email=self.email, password=SENHA_FORTE)
        self.url_pedido = reverse("authentication:password_reset")

    # -- helpers ------------------------------------------------------------
    def pedir_reset(self, email=None):
        return self.client.post(self.url_pedido, {"email": email or self.email})

    def link_do_email(self, mensagem=None):
        mensagem = mensagem or mail.outbox[-1]
        encontrado = re.search(r"/auth/reset/[^\s]+", mensagem.body)
        self.assertIsNotNone(encontrado, f"link nao encontrado no e-mail: {mensagem.body}")
        return encontrado.group(0)

    def abrir_link(self, caminho):
        """Segue o redirecionamento da tela de confirmacao para a de nova senha."""
        return self.client.get(caminho, follow=True)

    def post_nova_senha(self, caminho, senha1, senha2=None):
        """Faz o GET do link (grava o token na sessao) e envia a nova senha."""
        destino = self.client.get(caminho).url
        return self.client.post(
            destino, {"new_password1": senha1, "new_password2": senha2 or senha1}
        )

    # -- pedido do reset ----------------------------------------------------
    def test_get_renderiza_o_formulario_de_recuperacao(self):
        response = self.client.get(self.url_pedido)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/password_reset_form.html")
        self.assertContains(response, "Esqueceu sua senha")

    def test_post_com_email_cadastrado_envia_email_com_link(self):
        response = self.pedir_reset()

        self.assertRedirects(response, reverse("authentication:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)

        mensagem = mail.outbox[0]
        self.assertEqual(mensagem.to, [self.email])
        self.assertEqual(mensagem.from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertIn("/auth/reset/", mensagem.body)
        self.assertTrue(mensagem.subject)

    def test_post_com_email_desconhecido_nao_envia_nada(self):
        """Nao pode revelar se o e-mail existe (anti-enumeracao)."""
        response = self.pedir_reset(email="ninguem@unirotas.com")

        self.assertRedirects(response, reverse("authentication:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_post_com_usuario_inativo_nao_envia_email(self):
        self.user.is_active = False
        self.user.save()

        self.pedir_reset()

        self.assertEqual(len(mail.outbox), 0)

    def test_post_com_usuario_sem_senha_utilizavel_nao_envia_email(self):
        User.objects.create_user(email="sem.senha@unirotas.com", full_name="Sem Senha")

        self.pedir_reset(email="sem.senha@unirotas.com")

        self.assertEqual(len(mail.outbox), 0)

    def test_post_com_email_em_caixa_alta_funciona(self):
        self.pedir_reset(email="ALUNO@UNIROTAS.COM")

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.email])


    # -- consumo do link ---------------------------------------------------
    def test_fluxo_completo_redefine_a_senha(self):
        self.pedir_reset()
        caminho = self.link_do_email()

        # o GET da tela de confirmacao guarda o token na sessao e redireciona
        resposta_get = self.client.get(caminho)
        self.assertEqual(resposta_get.status_code, 302)
        self.assertIn("/set-password/", resposta_get.url)

        pagina = self.abrir_link(caminho)
        self.assertEqual(pagina.status_code, 200)
        self.assertTemplateUsed(pagina, "registration/password_reset_confirm.html")

        resposta_post = self.client.post(
            resposta_get.url,
            {"new_password1": SENHA_NOVA, "new_password2": SENHA_NOVA},
        )
        self.assertRedirects(
            resposta_post, reverse("authentication:password_reset_complete")
        )

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(SENHA_NOVA))
        self.assertFalse(self.user.check_password(SENHA_FORTE))

    def test_senha_redefinida_permite_login(self):
        self.pedir_reset()
        self.post_nova_senha(self.link_do_email(), SENHA_NOVA)
        self.client.logout()

        resposta = self.client.post(
            reverse("authentication:login"),
            {"email": self.email, "password": SENHA_NOVA},
        )

        self.assertRedirects(resposta, reverse("authentication:settings"))

    def test_link_nao_funciona_duas_vezes(self):
        self.pedir_reset()
        caminho = self.link_do_email()
        self.post_nova_senha(caminho, SENHA_NOVA)

        resposta = self.client.get(caminho, follow=True)

        self.assertFalse(resposta.context["validlink"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(SENHA_NOVA))

    def test_link_trocado_nao_funciona(self):
        self.pedir_reset()
        caminho = self.link_do_email()
        self.assertTrue(caminho.endswith("/"))
        caminho_trocado = caminho[:-1] + "x/"

        resposta = self.client.get(caminho_trocado, follow=True)

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(resposta.context["validlink"])

    def test_senha_fraca_e_recusada_no_reset(self):
        self.pedir_reset()

        resposta = self.post_nova_senha(self.link_do_email(), "123")

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.context["form"].errors)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(SENHA_FORTE))

    def test_senha_comum_e_recusada_pelo_validador_do_django(self):
        """No reset os AUTH_PASSWORD_VALIDATORS do Django sao aplicados."""
        self.pedir_reset()

        resposta = self.post_nova_senha(self.link_do_email(), "password1!")

        self.assertEqual(resposta.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password("password1!"))

    def test_senhas_divergentes_no_reset_nao_alteram_a_senha(self):
        self.pedir_reset()

        resposta = self.post_nova_senha(
            self.link_do_email(), SENHA_NOVA, "Outra@999"
        )

        self.assertEqual(resposta.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(SENHA_FORTE))

    def test_link_invalido_renderiza_pagina_de_erro(self):
        resposta = self.client.get(
            reverse(
                "authentication:password_reset_confirm",
                kwargs={"uidb64": "abc", "token": "token-invalido"},
            ),
            follow=True,
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(resposta.context["validlink"])


# ---------------------------------------------------------------------------
# 9. Seguranca
# ---------------------------------------------------------------------------
class CsrfTests(TestCase):
    """Views que mudam estado precisam exigir o token CSRF."""

    def test_post_sem_csrf_e_recusado(self):
        cliente = Client(enforce_csrf_checks=True)

        casos = [
            ("authentication:signup", dados_signup()),
            (
                "authentication:login",
                {"email": "aluno@unirotas.com", "password": SENHA_FORTE},
            ),
            ("authentication:toggle_notification", {}),
            ("authentication:logout", {}),
        ]

        for rota, dados in casos:
            with self.subTest(rota=rota):
                resposta = cliente.post(reverse(rota), dados)
                self.assertEqual(resposta.status_code, 403)

    def test_post_com_csrf_valido_funciona(self):
        cliente = Client(enforce_csrf_checks=True)
        resposta_get = cliente.get(reverse("authentication:signup"))
        token = resposta_get.cookies["csrftoken"].value

        resposta = cliente.post(
            reverse("authentication:signup"),
            dados_signup(email="com.csrf@unirotas.com"),
            HTTP_X_CSRFTOKEN=token,
        )

        self.assertRedirects(resposta, reverse("authentication:login"))
        self.assertTrue(User.objects.filter(email="com.csrf@unirotas.com").exists())


class SegurancaDeSenhaTests(TestCase):
    """A senha nao pode trafegar/ficar salva em texto puro."""

    @override_settings(
        PASSWORD_HASHERS=["django.contrib.auth.hashers.PBKDF2PasswordHasher"]
    )
    def test_senha_do_cadastro_fica_hasheada(self):
        self.client.post(
            reverse("authentication:signup"), dados_signup(email="hash@unirotas.com")
        )

        user = User.objects.get(email="hash@unirotas.com")
        self.assertNotEqual(user.password, SENHA_FORTE)
        self.assertNotIn(SENHA_FORTE, user.password)
        self.assertTrue(user.password.startswith("pbkdf2_sha256$"))
        self.assertTrue(user.check_password(SENHA_FORTE))

    def test_senha_do_convite_fica_hasheada(self):
        admin = criar_usuario(email="admin@unirotas.com", role=UserRole.ADMIN)
        link, _ = convidar(admin, "convidado@unirotas.com", UserRole.MANAGER)

        self.client.post(link, dados_convite())

        user = User.objects.get(email="convidado@unirotas.com")
        self.assertNotEqual(user.password, SENHA_FORTE)
        self.assertNotIn(SENHA_FORTE, user.password)

    def test_senha_sobrevive_ao_reset_com_hash(self):
        user = criar_usuario(email="reset@unirotas.com", password=SENHA_FORTE)
        self.client.post(
            reverse("authentication:password_reset"), {"email": "reset@unirotas.com"}
        )
        caminho = re.search(r"/auth/reset/[^\s]+", mail.outbox[0].body).group(0)
        destino = self.client.get(caminho).url

        self.client.post(
            destino, {"new_password1": SENHA_NOVA, "new_password2": SENHA_NOVA}
        )

        user.refresh_from_db()
        self.assertNotIn(SENHA_NOVA, user.password)
        self.assertTrue(user.check_password(SENHA_NOVA))


class EscalonamentoDeCargoTests(CacheLimpoTestCase):
    """Nenhum payload publico pode elevar cargo/flags do usuario criado."""

    def test_signup_publico_sempre_cria_estudante(self):
        self.client.post(
            reverse("authentication:signup"),
            dados_signup(
                email="tentativa@unirotas.com",
                role=UserRole.ADMIN,
                is_staff="True",
                is_superuser="True",
            ),
        )

        user = User.objects.get(email="tentativa@unirotas.com")
        self.assertEqual(user.role, UserRole.STUDENT)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_convite_de_gerente_nao_pode_virar_admin(self):
        gerente = criar_usuario(email="gerente@unirotas.com", role=UserRole.MANAGER)
        link, _ = convidar(gerente, "motorista@unirotas.com", UserRole.DRIVER)

        self.client.post(
            link, dados_convite(role=UserRole.ADMIN, is_superuser="True")
        )

        user = User.objects.get(email="motorista@unirotas.com")
        self.assertEqual(user.role, UserRole.DRIVER)
        self.assertFalse(user.is_superuser)

    def test_aluno_nao_consegue_gerar_convite_para_si_mesmo(self):
        aluno = criar_usuario(email="aluno@unirotas.com", role=UserRole.STUDENT)

        link = service.generate_elevated_signup_link(
            aluno.email, "copia@unirotas.com", UserRole.MANAGER
        )

        self.assertIsNone(link)


# ---------------------------------------------------------------------------
# 10. Falhas sistematicas encontradas - CORRIGIR COM URGENCIA
# ---------------------------------------------------------------------------
class FalhasUrgentesTests(MediaRootIsoladoMixin, CacheLimpoTestCase):
    """Testes vermelhos de proposito: descrevem o comportamento correto esperado.

    Cada teste aponta um problema real encontrado na app `authentication`.
    Enquanto o problema existir o teste falha - de proposito - para lembrar o
    time do que precisa ser corrigido antes de colocar o sistema em uso.
    """

    # -- 2. erros de formulario invisiveis para o usuario --------------------
    def test_login_deve_mostrar_o_erro_para_o_usuario(self):
        """URGENTE - falha silenciosa na tela de login.

        A view adiciona "E-mail ou senha inválidos." em `form_login`, mas
        `login.html` nao renderiza `form.errors`: o usuario volta para a mesma
        tela sem saber o que aconteceu.
        """
        criar_usuario(email="aluno@unirotas.com", password=SENHA_FORTE)

        response = self.client.post(
            reverse("authentication:login"),
            {"email": "aluno@unirotas.com", "password": "Errada@123"},
        )

        visiveis = mensagens_de_erro_visiveis(response, response.context["form_login"])
        self.assertTrue(
            visiveis,
            "A tela de login nao mostra nenhuma mensagem de erro ao usuario "
            "(o template nao renderiza form.errors).",
        )


    def test_troca_de_senha_deve_mostrar_o_erro_para_o_usuario(self):
        """URGENTE - falha silenciosa ao trocar senha.

        Se as senhas novas nao batem (ou sao fracas), `ChangePassword` fica
        invalido e a view apenas re-renderiza `change_password.html`, que tambem
        nao mostra `form.errors`: o usuario acha que a senha foi alterada.
        """
        usuario = criar_usuario(email="aluno@unirotas.com", password=SENHA_FORTE)
        self.client.force_login(usuario)

        response = self.client.post(
            reverse("authentication:change_password"),
            {
                "password": SENHA_FORTE,
                "new_password1": SENHA_NOVA,
                "new_password2": "Outra@999",
            },
        )

        visiveis = mensagens_de_erro_visiveis(response, response.context["form"])
        self.assertTrue(
            visiveis,
            "A tela de alteracao de senha nao mostra o erro de formulario "
            "(o usuario nao sabe que a troca falhou).",
        )

    def test_convite_deve_mostrar_erro_quando_email_ja_tem_conta(self):
        """URGENTE - convite para e-mail ja cadastrado falha em silencio.

        Se o e-mail do convite ja possui conta, `signup_form.is_valid()` e False
        e a view re-renderiza `signup_role.html` sem nenhuma explicacao.
        O convidado (futuro gestor/motorista) fica travado sem saber o motivo.
        """
        admin = criar_usuario(email="admin@unirotas.com", role=UserRole.ADMIN)
        criar_usuario(email="ja.existe@unirotas.com")
        link, _ = convidar(admin, "ja.existe@unirotas.com", UserRole.MANAGER)

        response = self.client.post(link, dados_convite())

        visiveis = mensagens_de_erro_visiveis(
            response, response.context["form_account"]
        )
        self.assertTrue(
            visiveis,
            "A tela de convite nao avisa que o e-mail ja possui conta "
            "(form_account.errors nao e renderizado).",
        )

    # -- 3. validadores oficiais de senha ignorados --------------------------
    def test_troca_de_senha_deve_rodar_os_validadores_do_django(self):
        """URGENTE - `ChangePassword` nao usa AUTH_PASSWORD_VALIDATORS.

        O form valida apenas o regex proprio, entao senhas parecidas com o
        e-mail/nome do usuario (ou da lista de senhas comuns) passam - diferente
        do reset de senha, que usa `validate_password`.
        """
        usuario = criar_usuario(
            email="carlos.eduardo@unirotas.com",
            full_name="Carlos Eduardo",
            password=SENHA_FORTE,
        )
        self.client.force_login(usuario)

        senha_proibida = "Carlos@2024"  # passa no regex do app
        with self.assertRaises(ValidationError, msg="premissa do teste"):
            validate_password(senha_proibida, usuario)

        self.client.post(
            reverse("authentication:change_password"),
            {
                "password": SENHA_FORTE,
                "new_password1": senha_proibida,
                "new_password2": senha_proibida,
            },
        )

        usuario.refresh_from_db()
        self.assertFalse(
            usuario.check_password(senha_proibida),
            "A senha foi trocada para uma senha reprovada pelos "
            "AUTH_PASSWORD_VALIDATORS (ChangePassword nao chama validate_password).",
        )

    def test_troca_de_senha_deve_avisar_quando_a_senha_atual_esta_errada(self):
        """URGENTE - a mensagem de senha atual incorreta nunca aparece na tela.

        A view coloca `error` no contexto, mas `change_password.html` nao
        renderiza `{{ error }}` nem `{{ form.errors }}`: o usuario tenta trocar a
        senha, erra a senha atual e recebe a mesma tela de volta, sem nenhum aviso.
        """
        usuario = criar_usuario(email="aluno@unirotas.com", password=SENHA_FORTE)
        self.client.force_login(usuario)

        response = self.client.post(
            reverse("authentication:change_password"),
            {
                "password": "Errada@123",
                "new_password1": SENHA_NOVA,
                "new_password2": SENHA_NOVA,
            },
        )

        self.assertContains(response, "não foi possivel")

    # -- 4. dados academicos/pessoais sem validacao ---------------------------
    def test_cadastro_deve_validar_periodo_entre_1_e_12(self):
        """URGENTE - `period` aceita 0 e valores acima do teto da UI (12).

        O widget sugere min=1/max=12, mas o model usa PositiveIntegerField sem
        validators, entao o servidor aceita qualquer inteiro >= 0.
        """
        for email, periodo in (
            ("periodo.zero@unirotas.com", 0),
            ("periodo.alto@unirotas.com", 99),
        ):
            with self.subTest(periodo=periodo):
                self.client.post(
                    reverse("authentication:signup"),
                    dados_signup(email=email, period=periodo),
                )

                self.assertFalse(
                    User.objects.filter(email=email).exists(),
                    f"O cadastro aceitou period={periodo} (a UI promete de 1 a 12).",
                )

    # -- 5. unicidade de e-mail case-sensitive --------------------------------
    def test_email_nao_deve_permitir_duplicidade_por_caixa(self):
        """URGENTE - unicidade de e-mail e case-sensitive no banco.

        O formulario baixa a caixa do e-mail, mas o banco nao: qualquer escrita
        que nao passe pelo form (admin, shell, outras apps/APIs) cria duas contas
        para a mesma pessoa ("Joao@x.com" e "joao@x.com"). Depois disso, a regra
        de unicidade do form nunca mais casa com o registro real.
        """
        User.objects.create(email="Joao.Silva@UniRota.com", password="x", full_name="A")

        with self.assertRaises(
            IntegrityError,
            msg="O banco permitiu duas contas para o mesmo e-mail "
            "diferindo apenas por maiuscula/minuscula (falta unicidade "
            "case-insensitive no model/migracao).",
        ):
            with transaction.atomic():
                User.objects.create(
                    email="joao.silva@unirota.com", password="x", full_name="B"
                )


# ---------------------------------------------------------------------------
# 11. Falhas aceitaveis para um MVP (documentadas, podem esperar)
# ---------------------------------------------------------------------------
class FalhasAceitaveisParaMVPTests(MediaRootIsoladoMixin, CacheLimpoTestCase):
    """Testes marcados com `expectedFailure`: documentam lacunas conhecidas.

    Eles falham hoje de forma esperada (o runner mostra "expected failures"),
    mas nao devem ser esquecidos: ficam aqui para serem resolvidos quando o
    fluxo principal do MVP estiver estavel. Se algum deles passar a passar, o
    runner acusa "unexpected success" e o decorator deve ser removido.
    """

    @expectedFailure
    def test_login_deve_respeitar_o_parametro_next(self):
        """MEDIA - `signin` ignora `?next=` e sempre manda para /auth/settings/.

        Quem clica em um link protegido (ex.: /auth/my_information/) e obrigado a
        fazer login e depois cai na tela de perfil, perdendo o destino original.
        Hoje: `login_required` adiciona `?next=`, mas a view nao usa o valor.
        """
        criar_usuario(email="aluno@unirotas.com", password=SENHA_FORTE)
        destino = reverse("authentication:my_information")
        self.client.get(destino)  # gera o redirect com ?next=

        response = self.client.post(
            reverse("authentication:login") + f"?next={destino}",
            {"email": "aluno@unirotas.com", "password": SENHA_FORTE},
        )

        self.assertRedirects(response, destino)

    @expectedFailure
    def test_recriar_convite_deve_gerar_token_novo(self):
        """BAIXA - o token do convite e deterministico (email + SECRET_KEY).

        `Signer` (sem timestamp) + `abort` + `generate` fazem o convite recriado
        ter exatamente o mesmo token, entao qualquer link antigo volta a
        funcionar depois da recriacao (link vazado em log/e-mail continua valido
        enquanto o SECRET_KEY nao mudar).
        """
        admin = criar_usuario(email="admin@unirotas.com", role=UserRole.ADMIN)
        _, token_antigo = convidar(admin, "convidado@unirotas.com", UserRole.MANAGER)

        novo_link = service.recreate_elevated_signup_link(
            admin.email, "convidado@unirotas.com", UserRole.MANAGER
        )

        self.assertNotEqual(token_do_link(novo_link), token_antigo)

    @expectedFailure
    def test_cadastro_publico_deve_exigir_confirmacao_de_email(self):
        """MEDIA - o cadastro publico ativa a conta sem confirmar o e-mail.

        Como qualquer pessoa consegue criar uma conta com um e-mail que nao e
        dela (sem clicar em nada), alguem pode "reservar" o endereco que um admin
        pretende convidar e travar aquele convite (negacao de servico no fluxo
        de convite). Nao ha escalonamento de cargo, mas atrapalha a operacao.
        """
        self.client.post(
            reverse("authentication:signup"), dados_signup(email="squat@unirotas.com")
        )

        usuario = User.objects.get(email="squat@unirotas.com")
        self.assertTrue(
            len(mail.outbox) >= 1 or not usuario.is_active,
            "A conta e criada 100% ativa e nenhum e-mail de confirmacao e enviado.",
        )

    @expectedFailure
    def test_login_deve_limitar_tentativas_repetidas(self):
        """MEDIA/ALTA - login nao tem throttling nem bloqueio por tentativas.

        Nada impede um ataque de forca bruta/dicionario contra a tela de login
        (nao existe rate limit por IP, usuario ou cache de tentativas).
        """
        criar_usuario(email="aluno@unirotas.com", password=SENHA_FORTE)
        url = reverse("authentication:login")

        for _ in range(10):
            self.client.post(url, {"email": "aluno@unirotas.com", "password": "Xxx@123"})

        response = self.client.post(
            url, {"email": "aluno@unirotas.com", "password": SENHA_FORTE}
        )

        self.assertIn(
            response.status_code,
            (423, 429),
            "Depois de 10 tentativas erradas o login deveria bloquear temporariamente.",
        )


    @expectedFailure
    def test_data_de_nascimento_no_futuro_deve_ser_recusada(self):
        """BAIXA - `birth_date` aceita datas futuras.

        O ModelForm so confere se a data e valida; nao existe validacao de
        intervalo (nem idade minima). Isso polui a base com idades negativas.
        """
        amanha = date.today() + timedelta(days=1)

        self.client.post(
            reverse("authentication:signup"),
            dados_signup(email="futuro@unirotas.com", birth_date=amanha.isoformat()),
        )

        self.assertFalse(User.objects.filter(email="futuro@unirotas.com").exists())

    @expectedFailure
    def test_avatar_antigo_deve_ser_removido_ao_trocar_a_foto(self):
        """BAIXA - a foto antiga fica orfa no disco (lixo acumulando em media/).

        `change_avatar` sobrescreve o campo do model sem apagar o arquivo antigo:
        cada troca de foto deixa um arquivo para tras.
        """
        usuario = criar_usuario(email="aluno@unirotas.com")
        self.client.force_login(usuario)
        url = reverse("authentication:change_avatar")

        self.client.post(
            url,
            {"profile_picture": SimpleUploadedFile("primeira.png", b"a", "image/png")},
        )
        usuario.refresh_from_db()
        caminho_antigo = self.arquivo_no_media(usuario.profile_picture.name)

        self.client.post(
            url,
            {"profile_picture": SimpleUploadedFile("segunda.png", b"b", "image/png")},
        )

        self.assertFalse(
            caminho_antigo.exists(), "A foto antiga continua ocupando espaco em media/."
        )

    @expectedFailure
    def test_servico_nao_deve_gerar_convite_para_email_que_ja_tem_conta(self):
        """MEDIA - o service envia convite para e-mail que ja possui conta.

        Hoje o e-mail e enviado, o convite fica no cache e o convidado descobre o
        problema so ao tentar concluir o cadastro (e sem mensagem de erro na
        tela). O esperado e barrar antes do envio.
        """
        admin = criar_usuario(email="admin@unirotas.com", role=UserRole.ADMIN)
        criar_usuario(email="ja.existe@unirotas.com")

        link = service.generate_elevated_signup_link(
            admin.email, "ja.existe@unirotas.com", UserRole.MANAGER
        )

        self.assertIsNone(link)
        self.assertEqual(len(mail.outbox), 0)


# Fim do arquivo de testes da app authentication.
# Se algum teste das classes de falhas comecar a passar, atualize/remova o
# decorator `expectedFailure` e tire o comentario da correcao no commit.

