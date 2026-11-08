from datetime import timedelta
import math
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from operation.models import Viagem, UsuarioDaViagem, Linha, ViagemParada
from management.models import TrechoViagem
from django.contrib import messages
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from authentication.models import UserRole
from django.db import IntegrityError
from metrics import service
from metrics.data_type import LastStopDTO, RouteDTO
#Viagem
from authentication.decorators import role_required

@login_required()
@role_required(UserRole.DRIVER)
def lista_viagens(request):
    viagem_atual = Viagem.objects.filter(status='em_andamento', rota__linha__motorista=request.user.personel_profile).order_by('rota__linha__horario_inicio').first()

    if not viagem_atual:
        viagem_atual = Viagem.objects.filter(status='aguardando', rota__linha__motorista=request.user.personel_profile).order_by('data').first()

    paradas_atual = []
    paradas_atual_quantidade = 0
    paradas_atual_feitas = 0
    proxima_parada = None
    moderador = None

    if viagem_atual:
        paradas_atual = ViagemParada.objects.filter(viagem=viagem_atual).order_by('id')
        paradas_atual_quantidade = paradas_atual.count()
        paradas_atual_feitas = paradas_atual.filter(status='Concluido').count()
        proxima_parada = paradas_atual.filter(status='Aguardando').first()
        moderador = UsuarioDaViagem.objects.filter(viagem=viagem_atual, moderador=True).first()

    context = {
        'viagem': viagem_atual,
        'moderador': moderador,
        'paradas': paradas_atual,
        'paradas_quantidade': paradas_atual_quantidade,
        'concluidos': paradas_atual_feitas,
        'proxima_parada': proxima_parada,
    }
    return render(request, 'lista_viagens.html', context)

@login_required()
@role_required([UserRole.DRIVER, UserRole.STUDENT])
def concluir_parada(request, parada_id):
    obj_parada = get_object_or_404(ViagemParada, pk=parada_id)

    #checagem para ver se o usuario que pediu essa requisição tem as permissões necessaria
    if request.user.role == UserRole.STUDENT:
        estudante = obj_parada.viagem.usuarios.filter(estudante=request.user.student_profile).first()
        if not estudante:
            return HttpResponseForbidden("Acesso negado.")
        if not estudante.moderador:
            return HttpResponseForbidden("Acesso negado.")
    elif request.user.personel_profile != obj_parada.viagem.rota.linha.motorista:
        return HttpResponseForbidden("Acesso negado.")

    service.set_last_stop_metrics(LastStopDTO(line=obj_parada.viagem.rota.linha, route=obj_parada.viagem.rota, current_stop=obj_parada.parada))
    
    proxima = obj_parada.concluir_busstop()

    if proxima:
        messages.success(request, f"Parada concluída! Próxima Parada sera: {proxima.parada.name}")
    else:
        messages.warning(request, "Parada concluída, mas nenhuma próxima parada foi encontrada.")

    if request.user.role == UserRole.STUDENT:
        return redirect('lista_linhas') 
        
    elif request.user.role == UserRole.DRIVER:
        return redirect('lista_viagens')
    else:
        return redirect('index')

@login_required()
@role_required([UserRole.DRIVER, UserRole.STUDENT])
def cancelar_parada(request, parada_id):
    obj_parada = get_object_or_404(ViagemParada, pk=parada_id)

    #checagem para ver se o usuario que pediu essa requisição tem as permissões necessaria
    if request.user.role == UserRole.STUDENT:
        estudante = obj_parada.viagem.usuarios.filter(estudante=request.user.student_profile).first()
        if not estudante:
            return HttpResponseForbidden("Acesso negado.")
        if not estudante.moderador:
            return HttpResponseForbidden("Acesso negado.")
    elif request.user.personel_profile != obj_parada.viagem.rota.linha.motorista:
        return HttpResponseForbidden("Acesso negado.")
    
    service.cancel_stop_metric(obj_parada.parada, obj_parada.viagem.rota)
    proxima = obj_parada.cancelar_busstop()

    if proxima:
        messages.success(request, f"Parada cancelada! Próxima Parada sera: ({proxima.parada.name})")
    else:
        messages.warning(request, "Parada cancelada, mas nenhuma próxima parada foi encontrada.")

    if request.user.role == UserRole.STUDENT:
        return redirect('lista_linhas') 
        
    elif request.user.role == UserRole.DRIVER:
        return redirect('lista_viagens')
    else:
        return redirect('index')

@login_required()
@role_required(UserRole.DRIVER)
def concluir_viagem(request, viagem_id):
    obj_viagem = get_object_or_404(Viagem, pk=viagem_id)
    
    if request.user.personel_profile != obj_viagem.rota.linha.motorista:
        return HttpResponseForbidden("Acesso negado.")
    
    proxima = obj_viagem.concluir(request.user.personel_profile)

    if proxima:
        messages.success(request, f"Viagem concluída! Próxima viagem sera: ({proxima.data})")
    else:
        messages.warning(request, "Viagem concluída, mas nenhuma próxima viagem foi encontrada.")
    service.set_route_as_done(obj_viagem.rota.linha, obj_viagem.rota)
    return redirect('lista_viagens')

@login_required()
@role_required(UserRole.DRIVER)
def comecar_viagem(request, viagem_id):
    obj_viagem = get_object_or_404(Viagem, pk=viagem_id)
    if request.user.personel_profile != obj_viagem.rota.linha.motorista:
        return HttpResponseForbidden("Acesso negado.")
    obj_viagem.comecar()
    return redirect('lista_viagens')

#Alunos

@login_required()
@role_required([UserRole.DRIVER, UserRole.STUDENT])
def lista_alunos(request, viagem_id):
    obj_viagem = get_object_or_404(Viagem, pk=viagem_id)
    
    if request.user.role == UserRole.STUDENT:
        estudante = obj_viagem.usuarios.filter(estudante=request.user.student_profile).first()
        if not estudante:
            return HttpResponseForbidden("Acesso negado.")
        if not estudante.moderador:
            return HttpResponseForbidden("Acesso negado.")
    elif request.user.personel_profile != obj_viagem.rota.linha.motorista:
        return HttpResponseForbidden("Acesso negado.")
    
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

@login_required()
@role_required([UserRole.DRIVER, UserRole.STUDENT])
def lista_alunos_moderador(request, viagem_id):
    obj_viagem = get_object_or_404(Viagem, pk=viagem_id)
    
    if request.user.role == UserRole.STUDENT:
        estudante = obj_viagem.usuarios.filter(estudante=request.user.student_profile).first()
        if not estudante:
            return HttpResponseForbidden("Acesso negado.")
        if not estudante.moderador:
            return HttpResponseForbidden("Acesso negado.")
    elif request.user.personel_profile != obj_viagem.rota.linha.motorista:
        return HttpResponseForbidden("Acesso negado.")
    
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
@login_required()
@role_required(UserRole.DRIVER)
def lista_moderadores(request, viagem_id):
    obj_viagem = get_object_or_404(Viagem, pk=viagem_id)

    if request.user.personel_profile != obj_viagem.rota.linha.motorista:
        return HttpResponseForbidden("Acesso negado.")

    alunos = UsuarioDaViagem.objects.filter(viagem=obj_viagem, presente=True).order_by('id')
    total_moderadores = UsuarioDaViagem.objects.filter(moderador=True, presente=True).count()
    return render(request, 'lista_moderadores.html', {
        'alunos': alunos,
        'viagens': obj_viagem, 
        'total_moderadores': total_moderadores,
        })

@login_required()
@role_required(UserRole.DRIVER)
def definir_moderador(request, usuario_viagem_id):
    aluno_clicado = get_object_or_404(UsuarioDaViagem, pk=usuario_viagem_id)
    viagem = aluno_clicado.viagem
    
    if request.user.personel_profile != viagem.rota.linha.motorista:
            return HttpResponseForbidden("Acesso negado.")
    
    if aluno_clicado.moderador:
        aluno_clicado.moderador = False
        aluno_clicado.save()
    else:
        UsuarioDaViagem.objects.filter(viagem=viagem, moderador=True).update(moderador=False)
        aluno_clicado.moderador = True
        aluno_clicado.save()

    return redirect('lista_moderadores', viagem.pk)

@login_required()
@role_required(UserRole.STUDENT)
def lista_linhas(request, indice=0):
    dia = Linha.dias_da_semana[timezone.localtime().weekday()]
    linhas = list(Linha.objects.filter(instituicoes_ofertadas=request.user.student_profile.institution,
        dias_ofertados__contains=dia[0], horario_fim__gte = timezone.localtime()).order_by('horario_inicio'))

    if not linhas:
        return render(request, 'lista_linhas.html', {'linha': None})

    indice = indice % len(linhas)
    linha_atual = linhas[indice]

    request.session['linha_selecionada_id'] = linha_atual.id

    proximo_indice = (indice + 1) % len(linhas)

    moderacao = UsuarioDaViagem.objects.filter(estudante=request.user.student_profile, moderador=True).first()
    
    #pegar as paradas das rotas
    viagem_atual = Viagem.objects.filter( status='em_andamento', rota__linha=linha_atual).order_by('data').first()

    if not viagem_atual:
        viagem_atual = Viagem.objects.filter(status='aguardando', rota__linha=linha_atual).order_by('data').first()
    
    paradas_atual = []
    paradas_atual_quantidade = 0
    paradas_atual_feitas = 0
    proxima_parada = None
    is_moderador = False

    if viagem_atual:
        paradas_atual = ViagemParada.objects.filter(viagem=viagem_atual).order_by('id')
        paradas_atual_quantidade = paradas_atual.count()
        paradas_atual_feitas = paradas_atual.filter(status='Concluido').count()
        proxima_parada = paradas_atual.filter(status='Aguardando').first()
        
        is_moderador = UsuarioDaViagem.objects.filter(viagem=viagem_atual, estudante=request.user.student_profile, moderador=True).exists()

    return render(request, 'lista_linhas.html', {
        'linha': linha_atual,
        'viagem':viagem_atual,
        'proximo_indice': proximo_indice,
        'total_linhas': len(linhas),
        'indice_atual': indice + 1,
        'moderacao': moderacao,
        'instituicao': request.user.student_profile.institution,
        'paradas': paradas_atual,
        'paradas_quantidade': paradas_atual_quantidade,
        'concluidos': paradas_atual_feitas,
        'proxima_parada': proxima_parada,
        'moderador': is_moderador,
    })

@login_required()
@role_required(UserRole.STUDENT)
def index_aluno(request):
    estudante = request.user.student_profile
    id_linha = request.session.get('linha_selecionada_id')
    inscricao = UsuarioDaViagem.objects.filter(estudante=estudante, viagem__status__in=["aguardando", "em_andamento"], viagem__rota__linha__pk=id_linha).first()
    if id_linha:
        linha_selecionada = Linha.objects.filter(pk=id_linha).first()
    else:
        linha_selecionada = Linha.objects.all().first()

    onibus = None
    if linha_selecionada:
        now = timezone.localtime()
        date = now.date()
        week_day = now.weekday()
    
        avaible_day = Linha.dias_da_semana[week_day] in linha_selecionada.dias_da_semana
        

        qs = Viagem.objects.filter(
                rota__linha=linha_selecionada,
                status__in=['em_andamento', 'concluida'],
                data__date = date
            )
        status_ida = not qs.filter(rota__direcao__icontains="IDA").exists()
        status_volta  = not qs.filter(rota__direcao__icontains="VOLTA").exists()
        direction_avaible = status_ida | status_volta
            

        time_avaible = (now.hour * 60 + now.minute) < (linha_selecionada.horario_fim.hour * 60 + linha_selecionada.horario_fim.minute)
        if avaible_day and direction_avaible and time_avaible:
            primeira_rota = linha_selecionada.linha_rota.first()
            if primeira_rota and primeira_rota.onibus:
                onibus = primeira_rota.onibus
        else:
            linha_selecionada = None

    #pegar as paradas das rotas
    viagem_atual = Viagem.objects.filter( status='em_andamento', rota__linha= linha_selecionada).order_by('data').first()

    if not viagem_atual:
        viagem_atual = Viagem.objects.filter(status='aguardando', rota__linha= linha_selecionada).order_by('data').first()
    
    atual_parada = None
    proxima_parada = None
    eta = None
    minutes_next = None
    minutes_last = None
    eta_current_stop = None

    if viagem_atual:
        paradas = ViagemParada.objects.filter(viagem=viagem_atual).order_by('id')
        aguardando = list(paradas.filter(status='Aguardando')[:2])
        atual_parada = paradas.filter(status='Concluido').last()
        eta = service.build_route_timeline_prediction(RouteDTO(
        line=viagem_atual.rota.linha,
        route=viagem_atual.rota
        ))
        if eta:
            eta_current_stop = eta.timeline[eta.current_order-1].status
            if eta.current_order < len(eta.timeline):
                minutes_next = timezone.localtime(eta.timeline[eta.current_order].eta).time()
                minutes_last = timezone.localtime(eta.timeline[-1].eta).time()
        if atual_parada:
            proxima_parada = aguardando[0] if len(aguardando) > 0 else None
        else:
            atual_parada = aguardando[0] if len(aguardando) > 0 else None
            proxima_parada = aguardando[1] if len(aguardando) > 1 else None
    if inscricao:
        inscricao = inscricao if inscricao.viagem.rota.linha == linha_selecionada else None
    
    context = {
        'linha_selecionada': linha_selecionada,
        'inscricao': inscricao,
        'instituicao': request.user.student_profile.institution,
        'onibus':onibus,
        'atual_parada':atual_parada,
        'eta_current_stop': eta_current_stop,
        'eta_next_stop_minutes': minutes_next,
        'eta_last_stop_minutes': minutes_last,
        'proxima_parada': proxima_parada,
    }
    return render(request, 'index_aluno.html', context)

from datetime import datetime, time, timedelta

def validate_line_available(linha, direcao, horario_saida):
    now = timezone.localtime()
    date = now.date()
    week_day = now.weekday()

    if Linha.dias_da_semana[week_day] not in linha.dias_da_semana:
        return False, "a viagem não é realizada neste dia"

    qs = Viagem.objects.filter(
        rota__linha=linha,
        status__in=['em_andamento', 'concluida'],
        data__date = date
    )
    status_ida, err_ida = not qs.filter(rota__direcao__icontains="IDA").exists(), "a viagem realizada para ida ja foi efetuado ou esta em andamento"
    status_volta, err_volta = not qs.filter(rota__direcao__icontains="VOLTA").exists(),  "a viagem realizada para volta ja foi efetuado ou esta em andamento"
    
    horario_saida = datetime.strptime(horario_saida, "%H:%M").time()
    horario_saida = horario_saida.hour * 60 + horario_saida.minute
    horario_maximo_saida = linha.horario_fim
    horario_maximo_saida = horario_maximo_saida.hour * 60 + horario_maximo_saida.minute
    
    if horario_saida:
        if horario_maximo_saida < horario_saida:
            return False, "o seu horario de saida estoura o limite de 30 minutos de tolerancia do horario de volta da linha"
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

@login_required()
@role_required(UserRole.STUDENT)
def alocar_aluno(request):
    if request.method == 'POST':
        id_linha = request.POST.get('id_linha')
        direcao = request.POST.get('direcao')
        horario_saida_aluno = request.POST.get('horario_saida_aluno')
        
        linha = get_object_or_404(Linha, pk=id_linha)
        available, err = validate_line_available(linha, direcao, horario_saida_aluno)
        if not available:
            messages.error(request, err)
            return redirect('index_aluno')

        if direcao != 'ida' and not horario_saida_aluno:
            messages.error(request, "O horário de saída é obrigatório para a volta.")
            return redirect('index_aluno')

        now = timezone.localtime()
        inicio = now.replace(
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
                                               data__lt=fim,
                                               data__gte=inicio
                                                ).first()
            viagem_volta = Viagem.objects.filter(rota=rota_volta,
                                                 status='aguardando',
                                                 data__lt=fim,
                                                 data__gte=inicio).first()

            
            if viagem_ida is None:
                viagem_ida = Viagem.objects.create(rota=rota_ida, status='aguardando', data=now.replace(hour=linha.horario_inicio.hour, minute=linha.horario_inicio.minute, second=0))
                viagem_ida.criar_paradas()

            if viagem_volta is None:
                viagem_volta = Viagem.objects.create(rota=rota_volta, status='aguardando', data=now.replace(hour=linha.horario_fim.hour, minute=linha.horario_fim.minute, second=0))
                viagem_volta.criar_paradas()
            
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
                                               data__lt=fim,
                                               data__gte=inicio).first()

            
            if viagem_dir is None:
                if direcao == "ida":
                    now = now.replace(hour=linha.horario_inicio.hour, minute=linha.horario_inicio.minute, second=0)
                else:
                    now = now.replace(hour=linha.horario_fim.hour, minute=linha.horario_fim.minute, second=0)
                viagem_dir = Viagem.objects.create(rota=rota_dir, status='aguardando', data=now)
                viagem_dir.criar_paradas()

            viagens_a_criar = [
                (viagem_dir, direcao)
            ]
        
        try:
            for viagem, direcao_percurso in viagens_a_criar:
                service.register_student_on_route(request.user, viagem.rota)
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
    
@login_required()
@role_required(UserRole.STUDENT)     
def cancelar_inscricao_na_viagem(request):
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
    for inscricao in inscricoes:
        service.destruct_student_from_route(request.user, inscricao.viagem.rota)
        inscricao.delete()
    
    messages.success(request, "Inscrições canceladas com sucesso.")

    usuarios = UsuarioDaViagem.objects.filter(viagem__rota__linha = request.POST.get("id_linha"))
    if not usuarios.exists():
        Viagem.objects.filter(rota__linha= request.POST.get("id_linha")).delete()

    return redirect('index_aluno')

@login_required()
@role_required(UserRole.STUDENT)       
def alterar_presenca(request):
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
    
        