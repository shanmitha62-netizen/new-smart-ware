/* =========================================================
   SMART WAREHOUSE OPERATIONS - FRONTEND APP JS
   ========================================================= */

document.addEventListener("DOMContentLoaded", function () {
    initSearchFilter();
    initNotificationsAutoDismiss();
});

/**
 * Live instant table search filter
 */
function initSearchFilter() {
    const searchInputs = document.querySelectorAll(".search-input, #tableSearch");
    searchInputs.forEach(input => {
        input.addEventListener("keyup", function () {
            const query = this.value.toLowerCase().trim();
            const table = this.closest(".dashboard-card, .card, body").querySelector("table");
            if (!table) return;

            const rows = table.querySelectorAll("tbody tr");
            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                if (text.includes(query)) {
                    row.style.display = "";
                } else {
                    row.style.display = "none";
                }
            });
        });
    });
}

/**
 * Auto dismiss flash alerts after 6 seconds
 */
function initNotificationsAutoDismiss() {
    const flashMessages = document.querySelectorAll(".flash-message");
    flashMessages.forEach(msg => {
        setTimeout(() => {
            msg.style.opacity = "0";
            msg.style.transition = "opacity 0.5s ease";
            setTimeout(() => msg.remove(), 500);
        }, 6000);
    });
}
