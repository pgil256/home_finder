/**
 * Pinellas Property Finder - Common Utilities
 * Toast notifications, skeleton loaders, and UI interactions
 */

// ============================================
// Toast Notification System
// ============================================

class ToastManager {
  constructor() {
    this.container = null;
    this.init();
  }

  init() {
    // Create toast container if it doesn't exist
    if (!document.getElementById('toast-container')) {
      this.container = document.createElement('div');
      this.container.id = 'toast-container';
      this.container.className = 'fixed bottom-4 right-4 z-50 flex flex-col gap-3 pointer-events-none';
      this.container.setAttribute('aria-live', 'polite');
      this.container.setAttribute('aria-atomic', 'true');
      document.body.appendChild(this.container);
    } else {
      this.container = document.getElementById('toast-container');
    }
  }

  show(message, type = 'info', duration = 4000) {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type} pointer-events-auto transform translate-x-full opacity-0`;
    toast.setAttribute('role', 'alert');

    const icons = {
      success: `<svg class="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
      </svg>`,
      error: `<svg class="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
      </svg>`,
      warning: `<svg class="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>`,
      info: `<svg class="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>`
    };

    toast.innerHTML = `
      <div class="flex items-center gap-3">
        ${icons[type] || icons.info}
        <p class="text-sm font-medium">${message}</p>
      </div>
      <button type="button" class="ml-4 flex-shrink-0 opacity-70 hover:opacity-100 transition-opacity" aria-label="Dismiss">
        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    `;

    // Close button handler
    toast.querySelector('button').addEventListener('click', () => this.dismiss(toast));

    this.container.appendChild(toast);

    // Animate in
    requestAnimationFrame(() => {
      toast.classList.remove('translate-x-full', 'opacity-0');
      toast.classList.add('translate-x-0', 'opacity-100');
    });

    // Auto dismiss
    if (duration > 0) {
      setTimeout(() => this.dismiss(toast), duration);
    }

    return toast;
  }

  dismiss(toast) {
    toast.classList.remove('translate-x-0', 'opacity-100');
    toast.classList.add('translate-x-full', 'opacity-0');
    setTimeout(() => toast.remove(), 300);
  }

  success(message, duration) {
    return this.show(message, 'success', duration);
  }

  error(message, duration) {
    return this.show(message, 'error', duration);
  }

  warning(message, duration) {
    return this.show(message, 'warning', duration);
  }

  info(message, duration) {
    return this.show(message, 'info', duration);
  }
}

// ============================================
// Skeleton Loader Utilities
// ============================================

class SkeletonLoader {
  static createPropertyCard() {
    return `
      <div class="property-card animate-pulse">
        <div class="skeleton h-48 rounded-t-2xl"></div>
        <div class="p-4 space-y-3">
          <div class="skeleton h-6 w-1/2"></div>
          <div class="skeleton h-4 w-3/4"></div>
          <div class="flex gap-4 mt-4">
            <div class="skeleton h-4 w-16"></div>
            <div class="skeleton h-4 w-16"></div>
            <div class="skeleton h-4 w-20"></div>
          </div>
          <div class="flex justify-between items-center mt-4">
            <div class="skeleton h-4 w-24"></div>
            <div class="skeleton h-8 w-20 rounded-lg"></div>
          </div>
        </div>
      </div>
    `;
  }

  static createPropertyGrid(count = 6) {
    let html = '<div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">';
    for (let i = 0; i < count; i++) {
      html += this.createPropertyCard();
    }
    html += '</div>';
    return html;
  }

  static createTableRow(columns = 5) {
    let html = '<tr class="animate-pulse">';
    for (let i = 0; i < columns; i++) {
      html += `<td class="px-4 py-3"><div class="skeleton h-4 w-full"></div></td>`;
    }
    html += '</tr>';
    return html;
  }

  static createTable(rows = 5, columns = 5) {
    let html = '<tbody>';
    for (let i = 0; i < rows; i++) {
      html += this.createTableRow(columns);
    }
    html += '</tbody>';
    return html;
  }

  static show(container, type = 'card', count = 6) {
    const element = typeof container === 'string' ? document.querySelector(container) : container;
    if (!element) return;

    element.setAttribute('data-skeleton-original', element.innerHTML);

    switch (type) {
      case 'card':
        element.innerHTML = this.createPropertyGrid(count);
        break;
      case 'table':
        element.innerHTML = this.createTable(count);
        break;
      default:
        element.innerHTML = this.createPropertyGrid(count);
    }
  }

  static hide(container) {
    const element = typeof container === 'string' ? document.querySelector(container) : container;
    if (!element) return;

    const original = element.getAttribute('data-skeleton-original');
    if (original) {
      element.innerHTML = original;
      element.removeAttribute('data-skeleton-original');
    }
  }
}

// ============================================
// Loading Button States
// ============================================

class LoadingButton {
  static start(button) {
    const btn = typeof button === 'string' ? document.querySelector(button) : button;
    if (!btn) return;

    btn.setAttribute('data-original-content', btn.innerHTML);
    btn.setAttribute('data-loading', 'true');
    btn.disabled = true;

    const text = btn.getAttribute('data-loading-text') || 'Loading...';
    btn.innerHTML = `
      <span class="spinner spinner-sm"></span>
      <span>${text}</span>
    `;
  }

  static stop(button) {
    const btn = typeof button === 'string' ? document.querySelector(button) : button;
    if (!btn) return;

    const original = btn.getAttribute('data-original-content');
    if (original) {
      btn.innerHTML = original;
    }
    btn.removeAttribute('data-loading');
    btn.removeAttribute('data-original-content');
    btn.disabled = false;
  }
}

// ============================================
// Smooth Scroll Utility
// ============================================

function smoothScrollTo(target, offset = 0) {
  const element = typeof target === 'string' ? document.querySelector(target) : target;
  if (!element) return;

  const top = element.getBoundingClientRect().top + window.pageYOffset - offset;
  window.scrollTo({
    top: top,
    behavior: 'smooth'
  });
}

// ============================================
// Intersection Observer for Animations
// ============================================

function initScrollAnimations() {
  const animatedElements = document.querySelectorAll('[data-animate]');

  if (animatedElements.length === 0) return;

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const animation = entry.target.getAttribute('data-animate');
        entry.target.classList.add('animate-' + animation);
        entry.target.classList.remove('opacity-0');
        observer.unobserve(entry.target);
      }
    });
  }, {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
  });

  animatedElements.forEach(el => {
    el.classList.add('opacity-0');
    observer.observe(el);
  });
}

// ============================================
// Form Utilities
// ============================================

function initFormEnhancements() {
  // Add loading state to forms with data-loading-form attribute
  document.querySelectorAll('form[data-loading-form]').forEach(form => {
    form.addEventListener('submit', function(e) {
      const submitBtn = form.querySelector('[type="submit"]');
      if (submitBtn) {
        LoadingButton.start(submitBtn);
      }
    });
  });

  // Number input formatting
  document.querySelectorAll('input[data-format="currency"]').forEach(input => {
    input.addEventListener('blur', function() {
      if (this.value) {
        const num = parseFloat(this.value.replace(/[^0-9.-]+/g, ''));
        if (!isNaN(num)) {
          this.value = num.toLocaleString('en-US');
        }
      }
    });
  });
}

// ============================================
// Copy to Clipboard
// ============================================

async function copyToClipboard(text, toast = null) {
  try {
    await navigator.clipboard.writeText(text);
    if (toast) {
      toast.success('Copied to clipboard!');
    }
    return true;
  } catch (err) {
    if (toast) {
      toast.error('Failed to copy to clipboard');
    }
    return false;
  }
}

// ============================================
// Debounce Utility
// ============================================

function debounce(func, wait = 300) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

// ============================================
// Initialize Everything
// ============================================

document.addEventListener('DOMContentLoaded', function() {
  // Initialize toast manager globally
  window.Toast = new ToastManager();

  // Initialize scroll animations
  initScrollAnimations();

  // Initialize form enhancements
  initFormEnhancements();

  // Legacy support for learn more button
  const learnMoreButton = document.getElementById('learnMoreButton');
  if (learnMoreButton) {
    learnMoreButton.addEventListener('click', function(event) {
      event.preventDefault();
      smoothScrollTo('#learn-more', 80);
    });
  }

  // Initialize copy buttons
  document.querySelectorAll('[data-copy]').forEach(btn => {
    btn.addEventListener('click', function() {
      const text = this.getAttribute('data-copy');
      copyToClipboard(text, window.Toast);
    });
  });
});

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    ToastManager,
    SkeletonLoader,
    LoadingButton,
    smoothScrollTo,
    copyToClipboard,
    debounce
  };
}

// Make utilities available globally
window.HomeFinder = {
  Toast: null, // Will be initialized on DOMContentLoaded
  Skeleton: SkeletonLoader,
  LoadingButton: LoadingButton,
  smoothScrollTo: smoothScrollTo,
  copyToClipboard: copyToClipboard,
  debounce: debounce
};
