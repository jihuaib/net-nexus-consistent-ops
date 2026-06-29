import { computed, onUnmounted, reactive, ref } from 'vue';

const INTERACTIVE_SELECTOR = [
  'button',
  'a',
  'input',
  'select',
  'textarea',
  '[contenteditable="true"]',
  '[data-no-drag]',
].join(',');

function clamp(value, min, max) {
  if (min > max) {
    return Math.round((min + max) / 2);
  }
  return Math.min(max, Math.max(min, value));
}

function isInteractiveTarget(target) {
  return Boolean(target?.closest?.(INTERACTIVE_SELECTOR));
}

export function useDraggableSurface(surfaceRef, options = {}) {
  const margin = Number(options.margin) || 12;
  const position = reactive({ x: 0, y: 0 });
  const dragging = ref(false);
  let dragState = null;

  const surfaceStyle = computed(() => ({
    transform: `translate3d(${position.x}px, ${position.y}px, 0)`,
  }));

  function getClampedPosition(x, y) {
    const surface = surfaceRef.value;
    if (!surface) {
      return { x, y };
    }

    const rect = surface.getBoundingClientRect();
    const baseLeft = rect.left - position.x;
    const baseTop = rect.top - position.y;
    const minX = margin - baseLeft;
    const maxX = window.innerWidth - margin - rect.width - baseLeft;
    const minY = margin - baseTop;
    const maxY = window.innerHeight - margin - rect.height - baseTop;

    return {
      x: clamp(x, minX, maxX),
      y: clamp(y, minY, maxY),
    };
  }

  function setPosition(x, y) {
    const next = getClampedPosition(x, y);
    position.x = next.x;
    position.y = next.y;
  }

  function moveDrag(event) {
    if (!dragState) {
      return;
    }
    setPosition(
      dragState.startXOffset + event.clientX - dragState.startX,
      dragState.startYOffset + event.clientY - dragState.startY
    );
  }

  function stopDrag(event) {
    if (!dragState) {
      return;
    }
    dragState.handle?.releasePointerCapture?.(event?.pointerId ?? dragState.pointerId);
    dragState = null;
    dragging.value = false;
    window.removeEventListener('pointermove', moveDrag);
    window.removeEventListener('pointerup', stopDrag);
    window.removeEventListener('pointercancel', stopDrag);
  }

  function startDrag(event) {
    if (event.button !== 0 || isInteractiveTarget(event.target) || !surfaceRef.value) {
      return;
    }
    event.preventDefault();

    dragState = {
      pointerId: event.pointerId,
      handle: event.currentTarget,
      startX: event.clientX,
      startY: event.clientY,
      startXOffset: position.x,
      startYOffset: position.y,
    };
    dragging.value = true;
    event.currentTarget?.setPointerCapture?.(event.pointerId);
    window.addEventListener('pointermove', moveDrag);
    window.addEventListener('pointerup', stopDrag);
    window.addEventListener('pointercancel', stopDrag);
  }

  function clampToViewport() {
    setPosition(position.x, position.y);
  }

  window.addEventListener('resize', clampToViewport);

  onUnmounted(() => {
    stopDrag();
    window.removeEventListener('resize', clampToViewport);
  });

  return {
    dragging,
    surfaceStyle,
    startDrag,
    clampToViewport,
  };
}
