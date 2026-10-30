// Mejoras progresivas: el catálogo y los formularios funcionan sin JavaScript.
document.querySelectorAll(".password-toggle").forEach((button) => {
  button.addEventListener("click", () => {
    const input = document.getElementById(button.getAttribute("aria-controls"));
    const showing = input.type === "password";
    input.type = showing ? "text" : "password";
    button.setAttribute("aria-pressed", String(showing));
    button.setAttribute("aria-label", showing ? "Ocultar contraseña" : "Mostrar contraseña");
  });
});

// Una imagen externa caída deja visible el icono local, sin romper el diseño de la ficha.
document.querySelectorAll(".product-image img, .detail-image img").forEach((image) => {
  const failed = () => image.classList.add("image-failed");
  image.addEventListener("error", failed);
  if (image.complete && !image.naturalWidth) failed();
});

// Carrusel sin dependencias: detener al enfocar, ocultar la pestaña o salir de pantalla.
document.querySelectorAll("[data-carousel]").forEach((carousel) => {
  const track = carousel.querySelector(".carousel-track");
  const slides = [...carousel.querySelectorAll("[data-slide]")];
  const pages = [...carousel.querySelectorAll("[data-slide-to]")];
  const pause = carousel.querySelector("[data-carousel-pause]");
  const status = carousel.querySelector("[data-carousel-status]");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let index = 0;
  let paused = reducedMotion.matches;
  let hovered = false;
  let visible = true;
  let timer;

  function schedule() {
    window.clearTimeout(timer);
    if (!paused && !hovered && visible && !document.hidden) {
      timer = window.setTimeout(() => show(index + 1), 7000);
    }
  }

  function setPaused(value) {
    paused = value;
    pause.textContent = paused ? "Reanudar banners" : "Pausar banners";
    schedule();
  }

  function show(next, manual = false) {
    index = (next + slides.length) % slides.length;
    track.style.transform = "translateX(-" + index * 100 + "%)";
    slides.forEach((slide, position) => {
      const inactive = position !== index;
      slide.inert = inactive;
      if (inactive) slide.setAttribute("aria-hidden", "true");
      else slide.removeAttribute("aria-hidden");
    });
    pages.forEach((button, position) => {
      if (position === index) button.setAttribute("aria-current", "true");
      else button.removeAttribute("aria-current");
    });
    // Los avances automáticos no interrumpen la lectura del lector de pantalla.
    if (manual) {
      status.textContent = "Banner " + (index + 1) + " de " + slides.length;
      setPaused(true);
    } else schedule();
  }

  pages.forEach((button) => button.addEventListener("click", () => show(Number(button.dataset.slideTo), true)));
  carousel.querySelector("[data-carousel-prev]").addEventListener("click", () => show(index - 1, true));
  carousel.querySelector("[data-carousel-next]").addEventListener("click", () => show(index + 1, true));
  pause.addEventListener("click", () => setPaused(!paused));
  carousel.addEventListener("mouseenter", () => { hovered = true; schedule(); });
  carousel.addEventListener("mouseleave", () => { hovered = false; schedule(); });
  carousel.addEventListener("focusin", (event) => {
    // Permitir activar pausa con el primer clic, sin que el foco invierta la acción.
    if (event.target !== pause) setPaused(true);
  });
  document.addEventListener("visibilitychange", schedule);
  reducedMotion.addEventListener("change", () => setPaused(reducedMotion.matches));
  const observer = new IntersectionObserver(([entry]) => {
    visible = entry.isIntersecting;
    schedule();
  });
  observer.observe(carousel);
  carousel.querySelector("[data-carousel-controls]").hidden = false;
  setPaused(paused);
});

// Edición progresiva: conservar el endpoint HTML como respaldo si JavaScript no está disponible.
const productModal = document.querySelector("#product-modal");
if (productModal && typeof productModal.showModal === "function") {
  const content = productModal.querySelector("[data-modal-content]");
  const status = productModal.querySelector("[data-modal-status]");
  const error = productModal.querySelector("[data-modal-error]");
  const title = productModal.querySelector("#modal-title");
  let opener;
  let loader;
  let saving = false;

  function showError(message) {
    error.textContent = message;
    error.hidden = false;
  }

  function closeEditor() {
    // Una escritura enviada debe terminar antes de permitir salir del formulario.
    if (!saving) productModal.close();
  }

  document.querySelectorAll("[data-product-edit]").forEach((link) => {
    link.addEventListener("click", async (event) => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      opener = link;
      const url = new URL(link.href);
      if (url.origin !== window.location.origin) return;
      url.searchParams.set("modal", "1");
      loader = new AbortController();
      content.replaceChildren();
      error.hidden = true;
      status.textContent = "Cargando producto…";
      status.hidden = false;
      content.setAttribute("aria-busy", "true");
      document.body.classList.add("modal-open");
      productModal.showModal();
      title.focus();
      try {
        const response = await fetch(url, {
          credentials: "same-origin",
          headers: { Accept: "application/json" },
          signal: loader.signal,
        });
        if (!response.ok || !response.headers.get("content-type")?.includes("application/json")) {
          throw new Error("load");
        }
        const result = await response.json();
        // El fragmento procede únicamente de Django y conserva el escapado de sus campos.
        content.innerHTML = result.html;
      } catch (failure) {
        if (failure.name !== "AbortError") showError("No pudimos cargar el producto. Cierra esta ventana e intenta de nuevo. Si tu sesión venció, vuelve a ingresar.");
      } finally {
        status.hidden = true;
        content.removeAttribute("aria-busy");
      }
    });
  });

  productModal.addEventListener("click", (event) => {
    if (event.target.closest("[data-modal-close]")) closeEditor();
    // Solo el clic fuera del rectángulo del diálogo cierra el fondo.
    if (event.target === productModal) {
      const rect = productModal.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) closeEditor();
    }
  });
  productModal.addEventListener("cancel", (event) => {
    if (saving) event.preventDefault();
  });
  productModal.addEventListener("close", () => {
    loader?.abort();
    document.body.classList.remove("modal-open");
    opener?.focus();
  });
  productModal.addEventListener("submit", async (event) => {
    const form = event.target.closest("[data-modal-form]");
    if (!form) return;
    event.preventDefault();
    if (saving) return;
    const payload = new FormData(form);
    saving = true;
    error.hidden = true;
    status.textContent = "Guardando cambios…";
    status.hidden = false;
    content.setAttribute("aria-busy", "true");
    const buttons = productModal.querySelectorAll("button");
    buttons.forEach((button) => { button.disabled = true; });
    try {
      // El CSRF viaja en FormData; el token de FastAPI permanece en la sesión del servidor.
      const response = await fetch(form.action, {
        method: "POST",
        credentials: "same-origin",
        headers: { Accept: "application/json" },
        body: payload,
      });
      if (!response.headers.get("content-type")?.includes("application/json")) throw new Error("session");
      const result = await response.json();
      if (response.ok && result.saved) {
        // Recargar la misma URL conserva filtros y obtiene precios y métricas vigentes.
        window.location.reload();
        return;
      }
      if (response.status === 422 && result.html) {
        content.innerHTML = result.html;
        const invalid = content.querySelector('[aria-invalid="true"]');
        invalid?.focus();
      } else throw new Error("save");
    } catch {
      // No reintentar automáticamente: una respuesta perdida puede corresponder a un guardado.
      showError("No pudimos confirmar el guardado. Conservamos tus datos; revisa la conexión y recarga el panel para comprobar el resultado antes de volver a guardar.");
    } finally {
      saving = false;
      status.hidden = true;
      content.removeAttribute("aria-busy");
      buttons.forEach((button) => { button.disabled = false; });
    }
  });
}
