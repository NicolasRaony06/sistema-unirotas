const role = document.querySelector('#id_role')
const formGroups = document.querySelectorAll('div.form-group')

role.addEventListener('change', () => {
    const roleValue = role.value
    formGroups.forEach((formGroup) => {
        const label = formGroup.querySelector('label')
        if (label && label.textContent.trim().includes("Instituição")){
            if (roleValue == 'STUDENT'){
                formGroup.style.display = '';
            }
            else {
                formGroup.style.display = 'none';
            }
        }
    })
})



