from django.shortcuts import render, get_object_or_404, redirect
from operation.models import Viagem, UsuarioDaViagem, Linha
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import reverse
#Viagem

def lista_viagens(request):
    viagem_atual = Viagem.objects.filter(status='em_andamento').order_by('data').first()
    

    if not viagem_atual:
        viagem_atual = Viagem.objects.filter(status='aguardando').order_by('data').first()
        
    moderador = UsuarioDaViagem.objects.filter(viagem=viagem_atual, moderador=True).first()

    return render(request, 'lista_viagens.html', {'viagem': viagem_atual, 'moderador': moderador})

def concluir_viagem(request, viagem_id):
    obj_viagem = get_object_or_404(Viagem, pk=viagem_id)
    proxima = obj_viagem.concluir()

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
    total_alunos = UsuarioDaViagem.objects.count()
    total_moderadores = UsuarioDaViagem.objects.filter(moderador=True).count()
    total_alunos_presentes = UsuarioDaViagem.objects.filter(presente=True).count()
    total_alunos_pendentes = UsuarioDaViagem.objects.filter(presente=False).count()
    return render(request, 'lista_alunos.html', {
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

def lista_linhas(request, indice = 0):
    linhas = list(Linha.objects.all().order_by('id'))

    if not linhas:
        return render(request, 'lista_linhas.html', {'linha': None})

    indice = indice % len(linhas)
    linha_atual = linhas[indice]

    request.session['linha_selecionada_id'] = linha_atual.id

    proximo_indice = (indice + 1) % len(linhas)

    return render(request, 'lista_linhas.html', {
        'linha': linha_atual,
        'proximo_indice': proximo_indice,
        'total_linhas': len(linhas),
        'indice_atual': indice + 1,
    })
    
def index_aluno(request):
    id_linha = request.session.get('linha_selecionada_id')
    if id_linha:
        linha_selecionada = Linha.objects.filter(pk=id_linha).first()
    else:
        linha_selecionada = Linha.objects.all().first()
    context = {
        'linha_selecionada': linha_selecionada
    }
    return render(request, 'index_aluno.html', context)
    