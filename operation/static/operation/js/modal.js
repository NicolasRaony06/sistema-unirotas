function abrirModal(urlDestino, titulo, mensagem, textoConfirmar = 'Confirmar', textoCancelar = 'Cancelar', variante = 'danger') {
    document.getElementById('app-modal-title').innerText = titulo;
    document.getElementById('app-modal-message').innerText = mensagem;

    const btnConfirm = document.getElementById('app-modal-confirm');
    btnConfirm.href = urlDestino;
    btnConfirm.innerText = textoConfirmar;

    document.getElementById('app-modal-cancel').innerText = textoCancelar;

    const modal = document.getElementById('app-modal');
    if (modal) {
        modal.classList.remove('app-modal--danger', 'app-modal--warning');
        modal.classList.add('app-modal--' + variante);
    }

    document.getElementById('app-modal-backdrop').classList.add('is-open');
}

function fecharModal() {
    document.getElementById('app-modal-backdrop').classList.remove('is-open');
}