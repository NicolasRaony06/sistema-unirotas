from django.shortcuts import render, get_object_or_404, redirect
from operation.models import Viagem, UsuarioDaViagem
from django.contrib import messages

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

def lista_alunos(request, viagem_id):
    obj_viagem = get_object_or_404(Viagem, pk=viagem_id)
    alunos = UsuarioDaViagem.objects.filter(viagem=obj_viagem).order_by('id')
    total_alunos = UsuarioDaViagem.objects.count()
    total_alunos_presentes = UsuarioDaViagem.objects.filter(presente=True).count()
    total_alunos_pendentes = UsuarioDaViagem.objects.filter(presente=False).count()
    return render(request, 'lista_alunos.html', {
        'alunos': alunos, 
        'viagens': obj_viagem, 
        'total': total_alunos,
        'presentes': total_alunos_presentes,
        'pendentes': total_alunos_pendentes,
        })
