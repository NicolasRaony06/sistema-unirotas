const qrcodePopup = document.getElementById("qrcodePopup")
const cancel = document.getElementById("cancel")
const copy = document.getElementById("copy")

if(qrcodePopup){
    qrcodePopup.showModal()

    cancel.addEventListener('click', () => {
        qrcodePopup.close()
    })

    copy.addEventListener('click', () => {
        const qrcodeLink = document.getElementById("qrcodeLink").href
        navigator.clipboard.writeText(qrcodeLink)
    })
}

