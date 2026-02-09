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
})();
