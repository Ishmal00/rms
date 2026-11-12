// Restaurant Management System - Frontend Helpers

document.addEventListener('DOMContentLoaded', function () {
  // Auto-dismiss alert banners after 5 seconds
  setTimeout(function () {
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(function (alert) {
      const bsAlert = new bootstrap.Alert(alert);
      bsAlert.close();
    });
  }, 5000);

  // Mobile sidebar toggle
  const sidebarToggle = document.getElementById('sidebarToggle');
  const sidebar = document.getElementById('sidebar');
  if (sidebarToggle && sidebar) {
    sidebarToggle.addEventListener('click', function () {
      sidebar.classList.toggle('show');
    });
  }

  // Initialize DataTables if jQuery & DataTables are loaded and tables are present
  if (window.jQuery && $.fn.DataTable) {
    $('.data-table').DataTable({
      responsive: true,
      pageLength: 10,
      language: {
        search: "_INPUT_",
        searchPlaceholder: "Search records..."
      }
    });
  }
});
