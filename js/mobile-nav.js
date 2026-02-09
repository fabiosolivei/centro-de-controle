// ============================================
// MOBILE NAVIGATION - Shared across all pages
// ============================================

(function() {
    'use strict';

    const PAGES = [
        { href: './',           icon: '🏠', label: 'Dashboard',     key: 'index' },
        { href: 'portfolio',    icon: '💼', label: 'Portfolio',      key: 'portfolio' },
        { href: 'mba',          icon: '🎓', label: 'MBA',           key: 'mba' },
        { href: 'work',         icon: '🏢', label: 'Work',          key: 'work' },
        { href: 'files',        icon: '📁', label: 'Arquivos',      key: 'files' },
        { href: 'observability',icon: '📊', label: 'Observability', key: 'observability' },
    ];

    // Detect current page
    const path = window.location.pathname;
    let currentKey = 'index';
    if (path.includes('portfolio')) currentKey = 'portfolio';
    else if (path.includes('mba')) currentKey = 'mba';
    else if (path.includes('work')) currentKey = 'work';
    else if (path.includes('files')) currentKey = 'files';
    else if (path.includes('observability')) currentKey = 'observability';
    else if (path.includes('project')) currentKey = 'project';

    // Build mobile menu HTML
    const navLinks = PAGES.map(p => 
        `<a href="${p.href}" class="mobile-nav-link${p.key === currentKey ? ' active' : ''}">
            <span class="mobile-nav-icon">${p.icon}</span>${p.label}
        </a>`
    ).join('\n            ');

    const menuHTML = `
    <div class="mobile-menu-overlay" id="mobile-menu-overlay"></div>
    <div class="mobile-menu" id="mobile-menu">
        <div class="mobile-menu-header">
            <h2>Menu</h2>
            <button class="mobile-menu-close" onclick="closeMobileMenu()" aria-label="Fechar menu">✕</button>
        </div>
        <nav class="mobile-menu-nav">
            ${navLinks}
        </nav>
    </div>

    <nav class="bottom-nav" aria-label="Mobile navigation">
        ${PAGES.slice(0, 5).map(p => 
            `<a href="${p.href}" class="nav-item${p.key === currentKey ? ' active' : ''}" aria-label="${p.label}">
                <span class="nav-icon">${p.icon}</span>
                <span class="nav-label">${p.label}</span>
            </a>`
        ).join('\n        ')}
    </nav>`;

    // Inject before </body>
    document.body.insertAdjacentHTML('beforeend', menuHTML);

    // Add hamburger button to header-actions (if not already present)
    const headerActions = document.querySelector('.header-actions');
    if (headerActions && !document.getElementById('hamburger-btn')) {
        const btn = document.createElement('button');
        btn.className = 'hamburger-btn';
        btn.id = 'hamburger-btn';
        btn.setAttribute('aria-label', 'Menu');
        btn.setAttribute('onclick', 'toggleMobileMenu()');
        btn.innerHTML = '☰';
        headerActions.insertBefore(btn, headerActions.firstChild);
    }

    // Global functions
    window.toggleMobileMenu = function() {
        document.getElementById('mobile-menu').classList.toggle('active');
        document.getElementById('mobile-menu-overlay').classList.toggle('active');
        document.body.style.overflow = document.getElementById('mobile-menu').classList.contains('active') ? 'hidden' : '';
    };

    window.closeMobileMenu = function() {
        document.getElementById('mobile-menu').classList.remove('active');
        document.getElementById('mobile-menu-overlay').classList.remove('active');
        document.body.style.overflow = '';
    };

    // Close on overlay click
    document.getElementById('mobile-menu-overlay')?.addEventListener('click', closeMobileMenu);

    // Close on Escape
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') closeMobileMenu();
    });

    // ============================================
    // PULL-TO-REFRESH (mobile touch gesture)
    // ============================================
    let pullStartY = 0;
    let pulling = false;
    const PULL_THRESHOLD = 80;

    // Create pull indicator
    const pullIndicator = document.createElement('div');
    pullIndicator.className = 'pull-indicator';
    pullIndicator.innerHTML = '<span class="pull-arrow">↓</span> Pull to refresh';
    pullIndicator.style.cssText = `
        position: fixed; top: -50px; left: 50%; transform: translateX(-50%);
        background: var(--bg-tertiary, #21262d); color: var(--text-secondary, #8b949e);
        padding: 8px 20px; border-radius: 20px; font-size: 0.8rem;
        transition: top 0.2s ease; z-index: 9999; pointer-events: none;
        border: 1px solid var(--border-color, #30363d);
    `;
    document.body.appendChild(pullIndicator);

    document.addEventListener('touchstart', function(e) {
        if (window.scrollY === 0) {
            pullStartY = e.touches[0].clientY;
            pulling = true;
        }
    }, { passive: true });

    document.addEventListener('touchmove', function(e) {
        if (!pulling) return;
        const pullDist = e.touches[0].clientY - pullStartY;
        if (pullDist > 20 && pullDist < 150) {
            pullIndicator.style.top = Math.min(pullDist - 50, 20) + 'px';
            if (pullDist > PULL_THRESHOLD) {
                pullIndicator.innerHTML = '<span class="pull-arrow" style="transform:rotate(180deg);display:inline-block;">↓</span> Release to refresh';
            }
        }
    }, { passive: true });

    document.addEventListener('touchend', function(e) {
        if (!pulling) return;
        pulling = false;
        pullIndicator.style.top = '-50px';
        pullIndicator.innerHTML = '<span class="pull-arrow">↓</span> Pull to refresh';

        const pullDist = e.changedTouches[0].clientY - pullStartY;
        if (pullDist > PULL_THRESHOLD && window.scrollY === 0) {
            // Trigger refresh — call page-specific reload if available
            if (typeof window.loadAllData === 'function') {
                window.loadAllData();
            } else {
                window.location.reload();
            }
        }
    }, { passive: true });
})();
