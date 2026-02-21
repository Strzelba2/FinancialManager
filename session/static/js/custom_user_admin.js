document.addEventListener("DOMContentLoaded", function() {
    const checkbox = document.querySelector("#id_is_two_factor");
    if (!checkbox) return;

    // Try to extract user ID from URL (last part before /change/)
    const pathParts = window.location.pathname.split("/").filter(Boolean);
    const userId = pathParts[3];

    console.log(pathParts)
    console.log(userId)

    checkbox.addEventListener("change", function() {
        if (userId) {
            const url = `/admin/qrcode/?user_id=${userId}`;
            window.location.href = url;
        }
    });
});