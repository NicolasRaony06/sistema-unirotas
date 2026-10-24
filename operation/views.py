from datetime import timedelta
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from operation.models import Viagem, UsuarioDaViagem, Linha
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from authentication.models import UserRole
from django.db import IntegrityError
#Viagem

def lista_viagens(request):
    viagem_atual = Viagem.objects.filter(status='em_andamento', rota__linha__motorista = request.user).order_by('rota__linha__horario_inicio').first()
    

    if not viagem_atual:
        viagem_atual = Viagem.objects.filter(status='aguardando', rota__linha__motorista = request.user).order_by('data').first()
        
    moderador = UsuarioDaViagem.objects.filter(viagem=viagem_atual, moderador=True).first()

    return render(request, 'lista_viagens.html', {'viagem': viagem_atual, 'moderador': moderador})

def concluir_viagem(request, viagem_id):
    obj_viagem = get_object_or_404(Viagem, pk=viagem_id)
    proxima = obj_viagem.concluir(request.user)

    if proxima:
        messages.success(request, f"Viagem concluída! Próxima viagem: ID {proxima.pk} ({proxima.data})")
    else:
        messages.warning(request, "Viagem concluída, mas nenhuma próxima viagem foi encontrada.")

    return redirect('lista_viagens')

def comecar_viagem(request, viagem_id):
    obj_viagem = get_object_or_404(Viagem, pk=viagem_id)
    obj_viagem.comecar()
    return redirect('lista_viagens')

#Alunos

def lista_alunos(request, viagem_id):
    obj_viagem = get_object_or_404(Viagem, pk=viagem_id)
    alunos = UsuarioDaViagem.objects.filter(viagem=obj_viagem).order_by('id')
    total_alunos = UsuarioDaViagem.objects.filter(viagem=obj_viagem).count()
    total_moderadores = UsuarioDaViagem.objects.filter(moderador=True, viagem=obj_viagem).count()
    total_alunos_presentes = UsuarioDaViagem.objects.filter(presente=True, viagem=obj_viagem).count()
    total_alunos_pendentes = UsuarioDaViagem.objects.filter(presente=False, viagem=obj_viagem).count()
    return render(request, 'lista_alunos.html', {
        'alunos': alunos, 
        'viagens': obj_viagem, 
        'total': total_alunos,
        'presentes': total_alunos_presentes,
        'pendentes': total_alunos_pendentes,
        'total_moderadores': total_moderadores,
        })
    
def lista_alunos_moderador(request, viagem_id):
    obj_viagem = get_object_or_404(Viagem, pk=viagem_id)
    alunos = UsuarioDaViagem.objects.filter(viagem=obj_viagem).order_by('id')
    total_alunos = UsuarioDaViagem.objects.filter(viagem=obj_viagem).count()
    total_moderadores = UsuarioDaViagem.objects.filter(moderador=True, viagem=obj_viagem).count()
    total_alunos_presentes = UsuarioDaViagem.objects.filter(presente=True, viagem=obj_viagem).count()
    total_alunos_pendentes = UsuarioDaViagem.objects.filter(presente=False, viagem=obj_viagem).count()
    return render(request, 'lista_alunos_moderador.html', {
        'alunos': alunos, 
        'viagens': obj_viagem, 
        'total': total_alunos,
        'presentes': total_alunos_presentes,
        'pendentes': total_alunos_pendentes,
        'total_moderadores': total_moderadores,
        })


#Moderadores
    
def lista_moderadores(request, viagem_id):
    obj_viagem = get_object_or_404(Viagem, pk=viagem_id)
    alunos = UsuarioDaViagem.objects.filter(viagem=obj_viagem, presente=True).order_by('id')
    total_moderadores = UsuarioDaViagem.objects.filter(moderador=True, presente=True).count()
    return render(request, 'lista_moderadores.html', {
        'alunos': alunos,
        'viagens': obj_viagem, 
        'total_moderadores': total_moderadores,
        })

def definir_moderador(request, usuario_viagem_id):
    aluno_clicado = get_object_or_404(UsuarioDaViagem, pk=usuario_viagem_id)
    viagem = aluno_clicado.viagem

    if aluno_clicado.moderador:
        aluno_clicado.moderador = False
        aluno_clicado.save()
    else:
        UsuarioDaViagem.objects.filter(viagem=viagem, moderador=True).update(moderador=False)
        aluno_clicado.moderador = True
        aluno_clicado.save()

    return redirect('lista_moderadores', viagem.pk)


def lista_linhas(request, indice=0):
    dia = Linha.dias_da_semana[timezone.localtime().weekday()]
    linhas = list(Linha.objects.filter(instituicoes_ofertadas=request.user.student_profile.institution,
        dias_ofertados__contains=dia[0], horario_fim__gte = timezone.localtime()).order_by('id'))

    if not linhas:
        return render(request, 'lista_linhas.html', {'linha': None})

    indice = indice % len(linhas)
    linha_atual = linhas[indice]

    request.session['linha_selecionada_id'] = linha_atual.id

    proximo_indice = (indice + 1) % len(linhas)

    moderacao = UsuarioDaViagem.objects.filter(
        estudante=request.user.student_profile,
        moderador=True
    ).first()
    
    return render(request, 'lista_linhas.html', {
        'linha': linha_atual,
        'proximo_indice': proximo_indice,
        'total_linhas': len(linhas),
        'indice_atual': indice + 1,
        'moderacao': moderacao,
        'instituicao': request.user.student_profile.institution
    })

# @login_required
def index_aluno(request):
    # if request.user.role != UserRole.STUDENT:
    #     messages.error(request, "Apenas estudantes podem se inscrever em uma viagem.")
    #     return redirect('index_aluno')
    estudante = request.user.student_profile
    inscricao = UsuarioDaViagem.objects.filter(estudante=estudante, viagem__status__in=["aguardando", "em_andamento"]).first()
    id_linha = request.session.get('linha_selecionada_id')
    if id_linha:
        linha_selecionada = Linha.objects.filter(pk=id_linha).first()
    else:
        linha_selecionada = Linha.objects.all().first()
    context = {
        'linha_selecionada': linha_selecionada,
        'inscricao': inscricao,
        'instituicao': request.user.student_profile.institution
    }
    return render(request, 'index_aluno.html', context)

def validate_line_available(linha, direcao):
    now = timezone.localtime()
    date = now.date()
    week_day = now.weekday()

    if Linha.dias_da_semana[week_day] not in linha.dias_da_semana:
        return False, "a viagem não é realizada neste dia"

    print(now.date(), Viagem.objects.all())

    qs = Viagem.objects.filter(
        rota__linha=linha,
        status__in=['em_andamento', 'concluida'],
        data__date = date
    )
    status_ida, err_ida = not qs.filter(rota__direcao__icontains="IDA").exists(), "a viagem realizada para ida ja foi efetuado ou esta em andamento"
    status_volta, err_volta = not qs.filter(rota__direcao__icontains="VOLTA").exists(),  "a viagem realizada para volta ja foi efetuado ou esta em andamento"
    print(qs.filter(rota__direcao__icontains="IDA").all())
    if direcao.lower() == "ida":
        return status_ida, err_ida
    elif direcao.lower() == "volta":
        return status_volta, err_volta
    else:
        if not status_ida and not status_volta:
            status_ida_volta, err_ida_volta = False, "a viagem não esta disponivel no momento, os trechos de ida e volta ja foram realizadas ou estão em andamento"
        else:
            status_ida_volta = status_ida if not status_ida else status_volta
            err_ida_volta = err_ida if not status_ida else err_volta
        return status_ida_volta, err_ida_volta

@login_required
def alocar_aluno(request):
    if request.user.role != UserRole.STUDENT:
        messages.error(request, "Apenas estudantes podem se inscrever em uma viagem.")
        return redirect('index_aluno')
    
    if request.method == 'POST':
        id_linha = request.POST.get('id_linha')
        direcao = request.POST.get('direcao')
        horario_saida_aluno = request.POST.get('horario_saida_aluno')
        
        linha = get_object_or_404(Linha, pk=id_linha)
        available, err = validate_line_available(linha, direcao)
        if not available:
            messages.error(request, err)
            return redirect('index_aluno')

        if direcao != 'ida' and not horario_saida_aluno:
            messages.error(request, "O horário de saída é obrigatório para a volta.")
            return redirect('index_aluno')

        now = timezone.localtime()
        data = now.date()
        inicio = timezone.localtime(now).replace(
        hour=0, minute=0, second=0, microsecond=0
)
        fim = inicio + timedelta(days=1)

        if direcao == "ida e volta":
            rota_ida = linha.linha_rota.filter(direcao__icontains="IDA").first()
            rota_volta = linha.linha_rota.filter(direcao__icontains="VOLTA").first()
            
            if not rota_ida or not rota_volta:
                messages.error(request, "Rotas de ida e/ou volta não encontradas para esta linha.")
                return redirect('index_aluno')
                
            viagem_ida = Viagem.objects.filter(rota=rota_ida,
                                               status='aguardando',
                                               data__lte=fim,
                                               data__gte=inicio
                                                ).first()
            viagem_volta = Viagem.objects.filter(rota=rota_volta,
                                                 status='aguardando',
                                                 data__lte=fim,
                                                 data__gte=inicio).first()
            print(viagem_ida, data)
            viagem_ida = viagem_ida if viagem_ida is not None else Viagem.objects.create(rota=rota_ida, status='aguardando', data=now)
            viagem_volta = viagem_volta if viagem_volta is not None else Viagem.objects.create(rota=rota_volta, status='aguardando', data=now)
            
            viagens_a_criar = [
                (viagem_ida, 'ida'),
                (viagem_volta, 'volta')
            ]

        else:
            rota_dir = linha.linha_rota.filter(direcao__icontains=direcao).first()
            if not rota_dir:
                messages.error(request, f"Rota de {direcao} não encontrada para esta linha.")
                return redirect('index_aluno')
                
            viagem_dir = Viagem.objects.filter(rota=rota_dir,
                                               status='aguardando',
                                               data__lte=fim,
                                               data__gte=inicio).first()
            viagem_dir = viagem_dir if viagem_dir is not None else Viagem.objects.create(rota=rota_dir, status='aguardando', data__date=now)

            viagens_a_criar = [
                (viagem_dir, direcao)
            ]
        
        try:
            for viagem, direcao_percurso in viagens_a_criar:
                UsuarioDaViagem.objects.create(
                    estudante=request.user.student_profile,
                    viagem=viagem,
                    direcao=direcao_percurso,
                    horario_saida_aluno=horario_saida_aluno
                )
        except IntegrityError:
            messages.error(request, "Você já está inscrito nesta viagem.")
            return redirect('index_aluno')
        
        messages.success(request, "Presença confirmada com sucesso!")
        return redirect('index_aluno')
    
@login_required        
def cancelar_inscricao_na_viagem(request):
    if request.user.role != UserRole.STUDENT:
        messages.error(request, "Apenas estudantes podem se inscrever em uma viagem.")
        return redirect('index_aluno')
        
    estudante = request.user.student_profile
    
    inscricoes = UsuarioDaViagem.objects.filter(
        estudante=estudante,
        viagem__status__in=['aguardando', "em_andamento"],
        #viagem = request.POST.get("id_viagem")
        viagem__rota__linha = request.POST.get("id_linha")
    )

    if not inscricoes.exists():
        messages.error(request, "Você não possui inscrições ativas em viagens pendentes.")
        return redirect('index_aluno')

    inscricoes.delete()
    
    messages.success(request, "Inscrições canceladas com sucesso.")

    usuarios = UsuarioDaViagem.objects.filter(viagem__rota__linha = request.POST.get("id_linha"))
    if not usuarios.exists():
        Viagem.objects.filter(rota__linha= request.POST.get("id_linha")).delete()

    return redirect('index_aluno')

@login_required        
def alterar_presenca(request):
    if request.user.role != UserRole.STUDENT:
        messages.error(request, "Apenas estudantes podem confirmar presenca em uma viagem.")
        return redirect('index_aluno')
    
    estudante = request.user.student_profile
    inscricao = UsuarioDaViagem.objects.filter(estudante=estudante, viagem__status__in=['aguardando', "em_andamento"],
            viagem=request.POST.get("id_viagem")
            ).first()

    if not inscricao:
        messages.error(request, "você não possui uma inscrição nessa viagem.")
        return redirect('index_aluno')
    
    if request.method == 'POST':
        if inscricao.presente:
            inscricao.presente = False
            inscricao.save()
            messages.success(request, "Presença cancelada com sucesso.")
            return redirect('index_aluno')
        else:
            inscricao.presente = True
            inscricao.save()
            messages.success(request, "Presença confirmada com sucesso.")
            return redirect('index_aluno')
    
        