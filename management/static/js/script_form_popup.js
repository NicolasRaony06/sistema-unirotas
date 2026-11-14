const popup = document.getElementById("formPopup")
const openPopup = document.getElementById("formDeleteBtn")
const closePopup = document.getElementById("cancel")

openPopup.addEventListener('click', () => {
    popup.showModal()
})

closePopup.addEventListener('click', () => {
    popup.close()
})