// Server-side Django forms still validate every submission without JavaScript.
document.addEventListener("DOMContentLoaded", function () {
    const dialog = document.querySelector("[data-error-dialog]");
    if (dialog && typeof dialog.showModal === "function") {
        dialog.showModal();
        dialog.querySelector("[data-close-dialog]").addEventListener("click", function () {
            dialog.close();
        });
    }

    document.querySelectorAll('form[method="post"]').forEach(function (form) {
        form.addEventListener("submit", function (event) {
            if (form.dataset.submitting === "true") {
                event.preventDefault();
                return;
            }
            form.dataset.submitting = "true";
            // Disabled buttons are excluded from POST data. Keep the chosen action.
            const submitter = event.submitter;
            if (submitter && submitter.name) {
                const action = document.createElement("input");
                action.type = "hidden";
                action.name = submitter.name;
                action.value = submitter.value;
                action.dataset.submitAction = "true";
                form.appendChild(action);
            }
            form.querySelectorAll('[type="submit"]').forEach(function (button) {
                button.disabled = true;
            });
        });
    });

    const expenseForm = document.querySelector("[data-expense-form]");
    if (expenseForm) {
        const category = expenseForm.querySelector('[name="category"]');
        const description = expenseForm.querySelector('[name="description"]');
        const examples = {
            Food: "e.g. Lunch",
            Transport: "e.g. Bus ticket",
            Entertainment: "e.g. Cinema ticket",
            Bills: "e.g. Electricity bill",
            Shopping: "e.g. Groceries",
            Other: "e.g. Other expense"
        };
        if (category && description) {
            const updateExample = function () {
                description.placeholder = examples[category.value] || "e.g. Lunch";
            };
            category.addEventListener("change", updateExample);
            updateExample();
        }
    }
});

// Back navigation may restore a form whose submit buttons were disabled.
window.addEventListener("pageshow", function () {
    document.querySelectorAll("form[data-submitting]").forEach(function (form) {
        delete form.dataset.submitting;
        form.querySelectorAll('[type="submit"]').forEach(function (button) {
            button.disabled = false;
        });
        form.querySelectorAll("[data-submit-action]").forEach(function (field) {
            field.remove();
        });
    });
});
