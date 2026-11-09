const popup = document.getElementById("formPopup")
const openPopup = document.getElementById("formDeleteBtn")
const closePopup = document.getElementById("cancel")
const confirmDeletion = document.getElementById("confirm")

openPopup.addEventListener('click', () => {
    popup.showModal()
})

closePopup.addEventListener('click', () => {
    popup.close()
})

confirmDeletion.addEventListener('click', () => {
    document.getElementById("formDelete").submit()
})