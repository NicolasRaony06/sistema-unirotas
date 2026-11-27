function abrirModal(titulo, mensagem, textoConfirmar = 'Confirmar', textoCancelar = 'Cancelar', variante = 'danger', link = null) {
    document.getElementById('app-modal-title').innerText = titulo;
    document.getElementById('app-modal-message').innerText = mensagem;
    document.getElementById('app-modal-cancel').innerText = textoCancelar;

    const btnConfirm = document.getElementById('app-modal-confirm');
    btnConfirm.innerText = textoConfirmar;
    btnConfirm.onclick = function () {
        fecharModal();
        if (link) window.location.href = link.href;
    };

    const modal = document.getElementById('app-modal');
    modal.classList.remove('app-modal--danger', 'app-modal--warning', 'app-modal--info', 'app-modal--success');
    modal.classList.add('app-modal--' + variante);

    document.getElementById('app-modal-backdrop').classList.add('is-open');
}

function modalSucesso(mensagem) {
    abrirModal('Tudo certo!', mensagem, 'Entendi', '', 'success');
}

function fecharModal() {
    document.getElementById('app-modal-backdrop').classList.remove('is-open');
}