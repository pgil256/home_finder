/**
 * Home Finder - Mobile Enhancements
 * Bottom sheets, swipe gestures, touch interactions
 */

// ============================================
// Bottom Sheet Component
// ============================================

class BottomSheet {
  constructor(element, options = {}) {
    this.element = typeof element === 'string' ? document.querySelector(element) : element;
    if (!this.element) return;

    this.options = {
      snapPoints: [0, 0.5, 0.9], // Percentages of screen height
      defaultSnap: 0,
      closeThreshold: 0.15,
      dragHandle: '.bottom-sheet-handle',
      overlay: true,
      ...options
    };

    this.overlay = null;
    this.handle = null;
    this.content = null;
    this.currentSnap = this.options.defaultSnap;
    this.isDragging = false;
    this.startY = 0;
    this.currentY = 0;
    this.startHeight = 0;

    this.init();
  }

  init() {
    // Add required classes
    this.element.classList.add('bottom-sheet');

    // Find or create handle
    this.handle = this.element.querySelector(this.options.dragHandle);
    if (!this.handle) {
      this.handle = document.createElement('div');
      this.handle.className = 'bottom-sheet-handle';
      this.handle.innerHTML = '<div class="bottom-sheet-handle-bar"></div>';
      this.element.prepend(this.handle);
    }

    // Find content container
    this.content = this.element.querySelector('.bottom-sheet-content');

    // Create overlay
    if (this.options.overlay) {
      this.overlay = document.createElement('div');
      this.overlay.className = 'bottom-sheet-overlay';
      this.element.parentNode.insertBefore(this.overlay, this.element);
      this.overlay.addEventListener('click', () => this.close());
    }

    // Touch event listeners
    this.handle.addEventListener('touchstart', this.onTouchStart.bind(this), { passive: true });
    document.addEventListener('touchmove', this.onTouchMove.bind(this), { passive: false });
    document.addEventListener('touchend', this.onTouchEnd.bind(this), { passive: true });

    // Mouse event listeners for desktop testing
    this.handle.addEventListener('mousedown', this.onMouseDown.bind(this));
    document.addEventListener('mousemove', this.onMouseMove.bind(this));
    document.addEventListener('mouseup', this.onMouseUp.bind(this));

    // Prevent body scroll when sheet is open
    this.element.addEventListener('touchmove', (e) => {
      if (this.currentSnap > 0) {
        const scrollTop = this.content?.scrollTop || 0;
        const scrollHeight = this.content?.scrollHeight || 0;
        const clientHeight = this.content?.clientHeight || 0;
        const atTop = scrollTop === 0;
        const atBottom = scrollTop + clientHeight >= scrollHeight;

        if ((atTop && e.touches[0].clientY > this.startY) ||
            (atBottom && e.touches[0].clientY < this.startY)) {
          // Allow drag
        } else if (!atTop && !atBottom) {
          e.stopPropagation();
        }
      }
    }, { passive: true });
  }

  onTouchStart(e) {
    this.isDragging = true;
    this.startY = e.touches[0].clientY;
    this.startHeight = this.element.offsetHeight;
    this.element.style.transition = 'none';
  }

  onTouchMove(e) {
    if (!this.isDragging) return;

    this.currentY = e.touches[0].clientY;
    const deltaY = this.startY - this.currentY;
    const newHeight = Math.max(0, Math.min(window.innerHeight * 0.95, this.startHeight + deltaY));

    this.element.style.height = `${newHeight}px`;

    // Update overlay opacity based on height
    if (this.overlay) {
      const progress = newHeight / (window.innerHeight * 0.9);
      this.overlay.style.opacity = Math.min(1, progress);
    }

    e.preventDefault();
  }

  onTouchEnd() {
    if (!this.isDragging) return;
    this.isDragging = false;
    this.element.style.transition = '';
    this.snapToNearest();
  }

  onMouseDown(e) {
    this.isDragging = true;
    this.startY = e.clientY;
    this.startHeight = this.element.offsetHeight;
    this.element.style.transition = 'none';
  }

  onMouseMove(e) {
    if (!this.isDragging) return;

    this.currentY = e.clientY;
    const deltaY = this.startY - this.currentY;
    const newHeight = Math.max(0, Math.min(window.innerHeight * 0.95, this.startHeight + deltaY));

    this.element.style.height = `${newHeight}px`;
  }

  onMouseUp() {
    if (!this.isDragging) return;
    this.isDragging = false;
    this.element.style.transition = '';
    this.snapToNearest();
  }

  snapToNearest() {
    const currentHeight = this.element.offsetHeight;
    const screenHeight = window.innerHeight;
    const currentPercent = currentHeight / screenHeight;

    // Find nearest snap point
    let nearestSnap = this.options.snapPoints[0];
    let minDistance = Math.abs(currentPercent - nearestSnap);

    for (const snap of this.options.snapPoints) {
      const distance = Math.abs(currentPercent - snap);
      if (distance < minDistance) {
        minDistance = distance;
        nearestSnap = snap;
      }
    }

    // Close if below threshold
    if (nearestSnap < this.options.closeThreshold) {
      this.close();
    } else {
      this.snapTo(nearestSnap);
    }
  }

  snapTo(snapPoint) {
    this.currentSnap = snapPoint;
    const height = window.innerHeight * snapPoint;
    this.element.style.height = `${height}px`;

    if (this.overlay) {
      this.overlay.style.opacity = snapPoint > 0 ? '1' : '0';
      this.overlay.style.pointerEvents = snapPoint > 0 ? 'auto' : 'none';
    }

    // Toggle body scroll
    document.body.style.overflow = snapPoint > 0.3 ? 'hidden' : '';
  }

  open(snapIndex = 1) {
    const snapPoint = this.options.snapPoints[snapIndex] || 0.5;
    this.element.classList.add('is-open');
    if (this.overlay) {
      this.overlay.classList.add('is-visible');
    }
    this.snapTo(snapPoint);
  }

  close() {
    this.currentSnap = 0;
    this.element.style.height = '0';
    this.element.classList.remove('is-open');

    if (this.overlay) {
      this.overlay.style.opacity = '0';
      this.overlay.style.pointerEvents = 'none';
      this.overlay.classList.remove('is-visible');
    }

    document.body.style.overflow = '';
  }

  toggle() {
    if (this.currentSnap > 0) {
      this.close();
    } else {
      this.open();
    }
  }
}

// ============================================
// Swipe Gesture Handler
// ============================================

class SwipeHandler {
  constructor(element, options = {}) {
    this.element = typeof element === 'string' ? document.querySelector(element) : element;
    if (!this.element) return;

    this.options = {
      threshold: 50,
      restraint: 100,
      allowedTime: 300,
      onSwipeLeft: null,
      onSwipeRight: null,
      onSwipeUp: null,
      onSwipeDown: null,
      ...options
    };

    this.startX = 0;
    this.startY = 0;
    this.startTime = 0;

    this.init();
  }

  init() {
    this.element.addEventListener('touchstart', this.onTouchStart.bind(this), { passive: true });
    this.element.addEventListener('touchend', this.onTouchEnd.bind(this), { passive: true });
  }

  onTouchStart(e) {
    const touch = e.changedTouches[0];
    this.startX = touch.pageX;
    this.startY = touch.pageY;
    this.startTime = Date.now();
  }

  onTouchEnd(e) {
    const touch = e.changedTouches[0];
    const distX = touch.pageX - this.startX;
    const distY = touch.pageY - this.startY;
    const elapsedTime = Date.now() - this.startTime;

    if (elapsedTime <= this.options.allowedTime) {
      if (Math.abs(distX) >= this.options.threshold && Math.abs(distY) <= this.options.restraint) {
        // Horizontal swipe
        if (distX > 0 && this.options.onSwipeRight) {
          this.options.onSwipeRight(this.element, distX);
        } else if (distX < 0 && this.options.onSwipeLeft) {
          this.options.onSwipeLeft(this.element, Math.abs(distX));
        }
      } else if (Math.abs(distY) >= this.options.threshold && Math.abs(distX) <= this.options.restraint) {
        // Vertical swipe
        if (distY > 0 && this.options.onSwipeDown) {
          this.options.onSwipeDown(this.element, distY);
        } else if (distY < 0 && this.options.onSwipeUp) {
          this.options.onSwipeUp(this.element, Math.abs(distY));
        }
      }
    }
  }
}

// ============================================
// Pull to Refresh
// ============================================

class PullToRefresh {
  constructor(element, options = {}) {
    this.element = typeof element === 'string' ? document.querySelector(element) : element;
    if (!this.element) return;

    this.options = {
      threshold: 80,
      maxPull: 120,
      onRefresh: null,
      refreshTimeout: 2000,
      ...options
    };

    this.indicator = null;
    this.isPulling = false;
    this.isRefreshing = false;
    this.startY = 0;
    this.currentY = 0;

    this.init();
  }

  init() {
    // Create pull indicator
    this.indicator = document.createElement('div');
    this.indicator.className = 'pull-to-refresh-indicator';
    this.indicator.innerHTML = `
      <div class="pull-to-refresh-spinner">
        <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
      </div>
      <span class="pull-to-refresh-text">Pull to refresh</span>
    `;
    this.element.parentNode.insertBefore(this.indicator, this.element);

    // Event listeners
    this.element.addEventListener('touchstart', this.onTouchStart.bind(this), { passive: true });
    this.element.addEventListener('touchmove', this.onTouchMove.bind(this), { passive: false });
    this.element.addEventListener('touchend', this.onTouchEnd.bind(this), { passive: true });
  }

  onTouchStart(e) {
    if (this.isRefreshing) return;
    if (window.scrollY > 0) return;

    this.startY = e.touches[0].clientY;
    this.isPulling = true;
  }

  onTouchMove(e) {
    if (!this.isPulling || this.isRefreshing) return;
    if (window.scrollY > 0) {
      this.isPulling = false;
      return;
    }

    this.currentY = e.touches[0].clientY;
    const pullDistance = Math.min(this.options.maxPull, this.currentY - this.startY);

    if (pullDistance > 0) {
      e.preventDefault();
      this.updateIndicator(pullDistance);
    }
  }

  onTouchEnd() {
    if (!this.isPulling || this.isRefreshing) return;

    const pullDistance = this.currentY - this.startY;

    if (pullDistance >= this.options.threshold) {
      this.triggerRefresh();
    } else {
      this.reset();
    }

    this.isPulling = false;
  }

  updateIndicator(distance) {
    const progress = Math.min(1, distance / this.options.threshold);
    this.indicator.style.transform = `translateY(${distance}px)`;
    this.indicator.style.opacity = progress;

    const spinner = this.indicator.querySelector('.pull-to-refresh-spinner');
    spinner.style.transform = `rotate(${progress * 180}deg)`;

    const text = this.indicator.querySelector('.pull-to-refresh-text');
    text.textContent = progress >= 1 ? 'Release to refresh' : 'Pull to refresh';

    this.element.style.transform = `translateY(${distance}px)`;
  }

  triggerRefresh() {
    this.isRefreshing = true;
    this.indicator.classList.add('is-refreshing');

    const text = this.indicator.querySelector('.pull-to-refresh-text');
    text.textContent = 'Refreshing...';

    if (this.options.onRefresh) {
      this.options.onRefresh(() => this.reset());
    } else {
      // Default: reload page after timeout
      setTimeout(() => {
        window.location.reload();
      }, this.options.refreshTimeout);
    }
  }

  reset() {
    this.indicator.style.transform = '';
    this.indicator.style.opacity = '0';
    this.element.style.transform = '';
    this.indicator.classList.remove('is-refreshing');
    this.isRefreshing = false;
  }
}

// ============================================
// Touch-friendly utilities
// ============================================

// Add active state feedback for touch
function initTouchFeedback() {
  const touchElements = document.querySelectorAll('.btn, .card-hover, .property-card, [data-touch-feedback]');

  touchElements.forEach(el => {
    el.addEventListener('touchstart', function() {
      this.classList.add('touch-active');
    }, { passive: true });

    el.addEventListener('touchend', function() {
      this.classList.remove('touch-active');
    }, { passive: true });

    el.addEventListener('touchcancel', function() {
      this.classList.remove('touch-active');
    }, { passive: true });
  });
}

// Haptic feedback (if supported)
function hapticFeedback(type = 'light') {
  if ('vibrate' in navigator) {
    switch (type) {
      case 'light':
        navigator.vibrate(10);
        break;
      case 'medium':
        navigator.vibrate(20);
        break;
      case 'heavy':
        navigator.vibrate([30, 10, 30]);
        break;
      case 'success':
        navigator.vibrate([10, 50, 10]);
        break;
      case 'error':
        navigator.vibrate([50, 30, 50, 30, 50]);
        break;
    }
  }
}

// Check if device is touch-enabled
function isTouchDevice() {
  return ('ontouchstart' in window) ||
         (navigator.maxTouchPoints > 0) ||
         (navigator.msMaxTouchPoints > 0);
}

// Add touch-device class to body
function initTouchDetection() {
  if (isTouchDevice()) {
    document.body.classList.add('touch-device');
  } else {
    document.body.classList.add('no-touch');
  }
}

// ============================================
// Sticky Action Bar (for mobile)
// ============================================

class StickyActionBar {
  constructor(element, options = {}) {
    this.element = typeof element === 'string' ? document.querySelector(element) : element;
    if (!this.element) return;

    this.options = {
      hideOnScroll: true,
      showThreshold: 100,
      ...options
    };

    this.lastScrollY = 0;
    this.isVisible = true;

    this.init();
  }

  init() {
    if (this.options.hideOnScroll) {
      window.addEventListener('scroll', this.onScroll.bind(this), { passive: true });
    }
  }

  onScroll() {
    const currentScrollY = window.scrollY;

    if (currentScrollY > this.options.showThreshold) {
      if (currentScrollY > this.lastScrollY && this.isVisible) {
        // Scrolling down - hide
        this.element.classList.add('is-hidden');
        this.isVisible = false;
      } else if (currentScrollY < this.lastScrollY && !this.isVisible) {
        // Scrolling up - show
        this.element.classList.remove('is-hidden');
        this.isVisible = true;
      }
    } else {
      // Near top - always show
      this.element.classList.remove('is-hidden');
      this.isVisible = true;
    }

    this.lastScrollY = currentScrollY;
  }
}

// ============================================
// Initialize on DOM ready
// ============================================

document.addEventListener('DOMContentLoaded', function() {
  initTouchDetection();
  initTouchFeedback();
});

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    BottomSheet,
    SwipeHandler,
    PullToRefresh,
    StickyActionBar,
    hapticFeedback,
    isTouchDevice
  };
}

// Make available globally
window.HomeFinder = window.HomeFinder || {};
Object.assign(window.HomeFinder, {
  BottomSheet,
  SwipeHandler,
  PullToRefresh,
  StickyActionBar,
  hapticFeedback,
  isTouchDevice
});
