# Prompt — Diagrama de Sequência: Fazer Check-in (UniRota)

Copie o texto abaixo e use-o para gerar o diagrama.

```text
Crie um diagrama de sequência UML para o caso de uso "FAZER CHECK-IN" do sistema
UniRota, utilizando exclusivamente a notação apresentada no material
"Modelos - Diagrama de Sequencia.pptx.pdf" (Profa. Me. Beatriz Soares):
atores, linhas de vida (objetos), mensagem de criação, mensagens síncronas e de
retorno, foco de controle/ativação, invariante de estado e fragmentos
combinados alt, opt, loop, break e critical, além de usos de interação
(<<include>> / <<extend>>). Use português do Brasil.

ESCOPO ASSUMIDO
"Fazer check-in" = o estudante confirma (ou cancela) sua presença em uma viagem
do dia, alternando UsuarioDaViagem.presente entre False e True. Implementação
principal: operation/views.py::alterar_presenca (rota "aluno/home/alterar",
name="alterar_presenca"). A confirmação inicial também aparece em
operation/views.py::alocar_aluno, que exibe "Presença confirmada com sucesso!"
ao criar a inscrição. Se o sentido desejado for check-in feito por motorista ou
moderador, mantenha a estrutura e troque apenas o ator e o ponto de entrada.

FONTES NO CÓDIGO (baseie-se nelas, não invente nomes)
- operation/urls.py -> "aluno/home", "aluno/home/alocar", "aluno/home/alterar"
- operation/views.py -> index_aluno, alocar_aluno, alterar_presenca,
  lista_alunos, lista_alunos_moderador
- operation/models.py -> Viagem, UsuarioDaViagem, ViagemParada
- management/models.py -> Rota, Linha, TrechoViagem, BusStop
- authentication/decorators.py -> login_required, role_required(STUDENT)

PARTICIPANTES SUGERIDOS (linhas de vida)
- ator: Estudante (autenticado, role = STUDENT)
- atores secundários: Motorista (DRIVER) e Moderador (estudante com
  UsuarioDaViagem.moderador = True), quando visualizam a lista de presença
- :TelaIndexAluno (index_aluno.html)
- :alterar_presenca (Django view)
- :UsuarioDaViagem (inscrição do estudante na viagem)
- :Viagem
- :ORM / Banco
- :Mensageria (django.contrib.messages) e :Redirect

DADOS E INVARIANTES DO MODELO (mostre como invariantes de estado, entre chaves)
- UsuarioDaViagem: estudante, viagem, direcao ('ida'/'volta'/'ida e volta'),
  horario_saida_aluno, presente (default False), instituicao, moderador
- UniqueConstraint(estudante, viagem) -> "um aluno por viagem"
- UniqueConstraint(viagem) quando moderador=True -> "um moderador por viagem"
- Viagem.status permitidos para check-in: 'aguardando' ou 'em_andamento'
- Viagem.data igual ao dia corrente (timezone.localtime().date())
- Apenas o próprio estudante pode alterar sua inscrição
- Mensagens: "Presença confirmada com sucesso." /
  "Presença cancelada com sucesso." / "você não possui uma inscrição nessa viagem."
- Redirecionamento final: redirect('index_aluno')

FLUXO PRINCIPAL A MODELAR
1. Estudante acessa GET /aluno/home; a view index_aluno carrega a linha
   selecionada da sessão, a viagem do dia e a inscrição atual; retorna
   index_aluno.html com o estado de presença.
2. Estudante clica em "Confirmar presença" e submete POST /aluno/home/alterar
   com id_viagem.
3. A view aplica @login_required e @role_required(UserRole.STUDENT).
4. A view consulta UsuarioDaViagem filtrando por estudante=request.user.student_profile,
   viagem=request.POST['id_viagem'], viagem__status__in=['aguardando','em_andamento']
   e viagem__data__date = hoje.
5. Se inscricao.presente == False: atribui True, save(), dispara mensagem de
   sucesso e redireciona para index_aluno. (Foco de controle ativo em save().)
6. Se inscricao.presente == True: atribui False, save(), mensagem
   "Presença cancelada com sucesso." e redireciona.

FLUXOS ALTERNATIVOS E DE EXCEÇÃO (obrigatórios, conforme o material)
- break: usuário anônimo ou role diferente de STUDENT -> acesso negado /
  redirecionamento para login. Interrompe o caso de uso.
- alt: inscrição não encontrada -> messages.error("você não possui uma inscrição
  nessa viagem.") + redirect('index_aluno').
- opt: alternância de presente (confirmar X cancelar), representando os dois
  estados da mesma inscrição.
- <<include>>: no fluxo de alocar_aluno, a criação de UsuarioDaViagem também
  "confirma presença" (registra a inscrição e exibe a mensagem de sucesso);
  represente como uso de interação, com criação de Viagem/ViagemParada quando
  ainda não existirem.
- critical: use transaction.atomic() apenas se modelar a criação acoplada
  (alocar_aluno), garantindo Viagem + ViagemParada + UsuarioDaViagem como uma
  unidade atômica.
- loop: percorra as viagens_a_criar (ida, volta ou "ida e volta") quando
  aplicável.

REGRAS DE MENSAGEM
- Siga a sintaxe do material: "variavel = nome(parametros): valor_de_retorno".
  Ex.: "inscricao = UsuarioDaViagem.objects.filter(...).first(): UsuarioDaViagem"
  Ex.: "inscricao.presente = alterar_presenca(id_viagem): True"
- Use seta sólida para chamadas síncronas, seta tracejada para retorno,
  mensagem <<create>> para criação de objetos e barras de ativação.
- Mesmo nome de método/campo que o código; nada de nomes genéricos inventados.

ENTREGÁVEIS
1. Código PlantUML (.puml) com title, actor, participant, create,
   activate/deactivate, note para invariantes e fragmentos alt/opt/loop/
   break/critical + rótulos <<include>>.
2. Imagens renderizadas em PNG e SVG.
3. Um arquivo .md com: fluxo principal, fluxos alternativos, exceção,
   tabela de notações do material usadas e rastreabilidade (views.py,
   models.py, urls.py, templates).

RESTRIÇÃO FINAL
Não use notação que não esteja no material. Não invente funcionalidades
(por exemplo, QR Code ou geolocalização) que não existam no código fornecido.
```
