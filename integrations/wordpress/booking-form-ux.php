<?php
/**
 * Source for the active Code Snippets entry:
 * "Booking - giao diện mobile và popup thông tin thiếu".
 *
 * Keep this file synchronized with that WordPress snippet. Run on the
 * front-end only; the page guard limits output to /booking/.
 */
add_action('wp_head', function () {
    if (!is_page('booking') && !is_page(3998)) {
        return;
    }
    ?>
    <style>
    @media (max-width: 767px) {
        .vera-booking-form { box-sizing: border-box; width: 100%; padding: 14px !important; }
        .vera-booking-form h2 { margin: 0 0 10px !important; font-size: 22px !important; line-height: 1.2 !important; }
        .vera-booking-form .vera-booking-fields {
            display: grid !important;
            grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
            gap: 8px 10px !important;
        }
        .vera-booking-form .vera-booking-fields > .vera-booking-field { min-width: 0; margin: 0 !important; }
        .vera-booking-form .vera-booking-fields > .vera-booking-field:nth-child(1),
        .vera-booking-form .vera-booking-fields > .vera-booking-field:nth-child(2) { grid-column: 1 / -1; }
        .vera-booking-form .vera-booking-fields > .vera-booking-field > p { margin: 0 !important; line-height: 1.2; }
        .vera-booking-form .vera-booking-fields > .vera-booking-field > p > br { display: none; }
        .vera-booking-form > .vera-booking-field > p,
        .vera-booking-form .vera-booking-note p { margin: 0 !important; }
        .vera-booking-form > p { margin: 6px 0 0 !important; }
        .vera-booking-form .vera-booking-field label {
            display: block; margin: 0 0 4px !important; font-size: 13px !important; line-height: 1.25 !important;
        }
        .vera-booking-form .vera-booking-fields input,
        .vera-booking-form .vera-booking-fields select {
            box-sizing: border-box; width: 100%; min-width: 0; min-height: 42px !important; height: 42px;
            margin: 0 !important; padding: 7px 10px !important; font-size: 15px !important;
        }
        .vera-booking-form .vera-booking-message { margin: 8px 0 0 !important; }
        .vera-booking-form .vera-booking-staff { margin: 8px 0 0 !important; }
        .vera-booking-form .vera-booking-staff p { margin: 0 !important; }
        .vera-booking-form .vera-booking-staff label { display: block; margin: 0 0 4px !important; font-size: 13px !important; }
        .vera-booking-form .vera-booking-staff select { box-sizing: border-box; width: 100%; min-height: 42px !important; height: 42px; margin: 0 !important; padding: 7px 10px !important; font-size: 15px !important; }
        .vera-booking-form .vera-booking-message p { margin: 0 !important; }
        .vera-booking-form .vera-booking-message textarea {
            box-sizing: border-box; min-height: 54px !important; height: 54px !important;
            margin: 0 !important; padding: 8px 10px !important; font-size: 14px !important;
        }
        .vera-booking-form input[type="submit"] {
            box-sizing: border-box; width: 100%; min-height: 46px !important; height: auto;
            margin: 8px 0 0 !important; padding: 10px 12px !important; font-size: 15px !important;
        }
        .vera-booking-form .vera-booking-note {
            display: flex; align-items: center; justify-content: center; gap: 12px; margin: 6px 0 0 !important;
        }
        .vera-booking-form .vera-booking-note .vera-hotline { font-size: 13px; }
        .vera-booking-form .vera-booking-note .vera-zalo-link img { width: 34px; height: 34px; }
    }
    @media (max-width: 360px) {
        .vera-booking-form { padding: 11px !important; }
        .vera-booking-form h2 { font-size: 20px !important; }
        .vera-booking-form .vera-booking-fields { gap: 7px 8px !important; }
        .vera-booking-form .vera-booking-fields input,
        .vera-booking-form .vera-booking-fields select {
            padding-right: 7px !important; padding-left: 7px !important; font-size: 14px !important;
        }
        .vera-booking-form .vera-booking-staff select { padding-right: 7px !important; padding-left: 7px !important; font-size: 14px !important; }
    }
    .vera-booking-popup {
        position: fixed; inset: 0; z-index: 999999; display: flex; align-items: center; justify-content: center;
        box-sizing: border-box; padding: 16px; background: rgba(14, 35, 27, .58);
    }
    .vera-booking-popup__dialog {
        width: min(100%, 420px); box-sizing: border-box; padding: 22px; border: 1px solid #d8e4db;
        border-radius: 16px; background: #fffdf4; color: #183c30; box-shadow: 0 18px 50px rgba(0, 0, 0, .24);
    }
    .vera-booking-popup__dialog h3 { margin: 0 0 8px; color: #184d3a; font-size: 21px; line-height: 1.3; }
    .vera-booking-popup__dialog p { margin: 0 0 8px; font-size: 15px; }
    .vera-booking-popup__dialog ul { margin: 0 0 18px; padding-left: 21px; }
    .vera-booking-popup__dialog li { margin: 4px 0; }
    .vera-booking-popup__close {
        min-height: 42px; padding: 9px 18px; border: 0; border-radius: 9px; background: #205b46; color: #fff;
        font: inherit; font-weight: 700; cursor: pointer;
    }
    .vera-booking-popup__close:focus-visible { outline: 3px solid #d39c34; outline-offset: 3px; }
    @media (prefers-reduced-motion: no-preference) {
        .vera-booking-popup__dialog { animation: vera-booking-popup-in .16s ease-out; }
        @keyframes vera-booking-popup-in {
            from { opacity: 0; transform: translateY(8px) scale(.98); }
            to { opacity: 1; transform: translateY(0) scale(1); }
        }
    }
    </style>
    <?php
}, 90);

add_action('wp_footer', function () {
    if (!is_page('booking') && !is_page(3998)) {
        return;
    }
    ?>
    <script>
    (function () {
        var employeesCache = null;
        var pendingRequest = null;

        function getStaffSelects() {
            return Array.prototype.slice.call(document.querySelectorAll('.vera-booking-form select[name="requested-staff"]'));
        }

        function renderStaffOptions(selects, employees, error) {
            selects.forEach(function (select) {
                select.innerHTML = '';
                var blank = document.createElement('option');
                blank.value = '';
                blank.textContent = error ? 'Không thể tải nhân viên lúc này' : 'Không yêu cầu nhân viên';
                select.appendChild(blank);
                if (error) {
                    select.disabled = true;
                    select.setAttribute('aria-label', 'Không tải được danh sách nhân viên đang đi làm');
                    return;
                }
                select.disabled = false;
                select.removeAttribute('aria-label');
                employees.forEach(function (employee) {
                    if (!employee || !employee.value || !employee.label) return;
                    var option = document.createElement('option');
                    option.value = employee.value;
                    option.textContent = employee.label;
                    select.appendChild(option);
                });
                if (select.options.length === 1) {
                    select.options[0].textContent = 'Hôm nay chưa có nhân viên trong ca';
                }
            });
        }

        function loadWorkingStaff() {
            var selects = getStaffSelects();
            if (!selects.length) return;
            if (employeesCache) {
                renderStaffOptions(selects, employeesCache, false);
                return;
            }
            if (pendingRequest) return;
            var endpoint = (window.wpApiSettings && window.wpApiSettings.root)
                ? window.wpApiSettings.root + 'vera/v1/booking-staff'
                : window.location.origin + '/wp-json/vera/v1/booking-staff';
            pendingRequest = fetch(endpoint, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
                .then(function (response) { if (!response.ok) throw new Error('unavailable'); return response.json(); })
                .then(function (data) {
                    employeesCache = Array.isArray(data.employees) ? data.employees : [];
                    renderStaffOptions(getStaffSelects(), employeesCache, false);
                })
                .catch(function () {
                    renderStaffOptions(getStaffSelects(), [], true);
                })
                .finally(function () {
                    pendingRequest = null;
                });
        }
        document.addEventListener('wpcf7init', loadWorkingStaff);
        loadWorkingStaff();

        function findBookingForm(target) {
            if (!target) return null;
            var form = target.matches && target.matches('form.wpcf7-form')
                ? target
                : target.querySelector && target.querySelector('form.wpcf7-form');
            return form && form.querySelector('.vera-booking-form') ? form : null;
        }
        document.addEventListener('wpcf7invalid', function (event) {
            var form = findBookingForm(event.target);
            if (!form) return;
            window.setTimeout(function () {
                var invalid = Array.prototype.slice.call(form.querySelectorAll('.wpcf7-not-valid'));
                if (!invalid.length) return;
                var labels = [];
                invalid.forEach(function (field) {
                    var group = field.closest('.vera-booking-field');
                    var label = group && group.querySelector('label');
                    var name = (label ? label.textContent : field.name || 'Thông tin').replace(/\s*\*/g, '').trim();
                    if (name && labels.indexOf(name) === -1) labels.push(name);
                });
                var old = document.querySelector('.vera-booking-popup');
                if (old) old.remove();
                var overlay = document.createElement('div');
                overlay.className = 'vera-booking-popup';
                overlay.setAttribute('role', 'alertdialog');
                overlay.setAttribute('aria-modal', 'true');
                overlay.setAttribute('aria-labelledby', 'vera-booking-popup-title');
                var dialog = document.createElement('div');
                dialog.className = 'vera-booking-popup__dialog';
                var title = document.createElement('h3');
                title.id = 'vera-booking-popup-title';
                title.textContent = 'Bạn cần bổ sung thông tin';
                var intro = document.createElement('p');
                intro.textContent = 'Vui lòng kiểm tra các mục sau:';
                var list = document.createElement('ul');
                labels.forEach(function (name) {
                    var item = document.createElement('li');
                    item.textContent = name;
                    list.appendChild(item);
                });
                var close = document.createElement('button');
                close.type = 'button';
                close.className = 'vera-booking-popup__close';
                close.textContent = 'Đã hiểu';
                dialog.append(title, intro, list, close);
                overlay.appendChild(dialog);
                document.body.appendChild(overlay);
                var first = invalid[0];
                function closePopup() {
                    overlay.remove();
                    document.removeEventListener('keydown', onKey);
                    if (first && first.isConnected) {
                        first.focus({preventScroll: true});
                        first.scrollIntoView({behavior: 'smooth', block: 'center'});
                    }
                }
                function onKey(event) {
                    if (event.key === 'Escape') closePopup();
                }
                close.addEventListener('click', closePopup);
                overlay.addEventListener('click', function (event) {
                    if (event.target === overlay) closePopup();
                });
                document.addEventListener('keydown', onKey);
                close.focus();
            }, 0);
        });
    })();
    </script>
    <?php
}, 100);
