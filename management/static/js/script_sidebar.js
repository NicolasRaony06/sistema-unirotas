document.addEventListener("DOMContentLoaded", function() {
const activeItem = document.querySelector('.sidebar-nav a.nav-link.selected');

if (activeItem) {
    activeItem.scrollIntoView({
    behavior: 'smooth',
    block: 'nearest' 
    });
}
});
