(function () {
    'use strict';

    var config = window.vaysfAdminCacheGuard || {};
    var renderedVersion = String(config.renderedVersion || '');
    var activeVersion = '';
    var isStale = false;

    if (!config.ajaxUrl || !config.nonce || !renderedVersion) {
        return;
    }

    function findNoticeAnchor() {
        return document.querySelector('.wrap h1') || document.querySelector('.wrap') || document.body.firstChild;
    }

    function showReloadNotice(version) {
        var existing = document.getElementById('vaysf-admin-cache-guard-notice');
        if (existing) {
            return;
        }

        var notice = document.createElement('div');
        notice.id = 'vaysf-admin-cache-guard-notice';
        notice.className = 'notice notice-warning';

        var message = document.createElement('p');
        message.appendChild(document.createTextNode(config.reloadMessage || 'Sports Fest was updated after this page loaded. Reload this page before saving.'));
        if (version) {
            message.appendChild(document.createTextNode(' Active version: ' + version + '.'));
        }

        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'button button-primary';
        button.textContent = config.reloadLabel || 'Reload now';
        button.addEventListener('click', function () {
            window.location.reload();
        });

        message.appendChild(document.createTextNode(' '));
        message.appendChild(button);
        notice.appendChild(message);

        var anchor = findNoticeAnchor();
        if (anchor && anchor.parentNode) {
            anchor.parentNode.insertBefore(notice, anchor.nextSibling);
        } else {
            document.body.insertBefore(notice, document.body.firstChild);
        }
    }

    function handleVersionResponse(payload) {
        var version = payload && payload.success && payload.data ? String(payload.data.version || '') : '';
        if (!version || version === renderedVersion) {
            return;
        }

        activeVersion = version;
        isStale = true;
        showReloadNotice(activeVersion);
    }

    function checkVersion() {
        if (isStale) {
            showReloadNotice(activeVersion);
            return;
        }

        var body = new URLSearchParams();
        body.set('action', 'vaysf_plugin_version');
        body.set('nonce', config.nonce);
        body.set('rendered_version', renderedVersion);

        window.fetch(config.ajaxUrl, {
            method: 'POST',
            credentials: 'same-origin',
            cache: 'no-store',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Cache-Control': 'no-cache'
            },
            body: body.toString()
        })
            .then(function (response) {
                return response.ok ? response.json() : null;
            })
            .then(handleVersionResponse)
            .catch(function () {
                // A failed freshness check should not block event-day work.
            });
    }

    document.addEventListener('submit', function (event) {
        if (!isStale) {
            return;
        }

        event.preventDefault();
        event.stopPropagation();
        showReloadNotice(activeVersion);
    }, true);

    window.addEventListener('focus', checkVersion);
    window.addEventListener('pageshow', checkVersion);
    setTimeout(checkVersion, 1000);
    setInterval(checkVersion, 60000);
}());
