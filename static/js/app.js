// Глобальные утилиты для веб-приложения

function showToast(message, type = 'success') {
    // Простая реализация уведомлений (можно заменить на библиотеку)
    const colors = {
        success: 'bg-green-500',
        error: 'bg-red-500',
        warning: 'bg-yellow-500'
    };
    
    const toast = document.createElement('div');
    toast.className = `fixed top-4 right-4 ${colors[type]} text-white px-6 py-3 rounded-lg shadow-lg z-50 transition-opacity duration-300`;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function confirmDelete(message, callback) {
    if (confirm(message)) {
        callback();
    }
}
