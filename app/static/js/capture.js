(function () {
  "use strict";

  const video = document.getElementById("video");
  const preview = document.getElementById("preview");
  const canvas = document.getElementById("canvas");
  const captureGuide = document.getElementById("capture-guide");
  const cameraError = document.getElementById("camera-error");
  const ocrStatus = document.getElementById("ocr-status");

  const btnCapture = document.getElementById("btn-capture");
  const btnRetake = document.getElementById("btn-retake");

  const fieldApellidos = document.getElementById("apellidos");
  const fieldNombres = document.getElementById("nombres");
  const fieldRut = document.getElementById("rut");
  const fieldFecha = document.getElementById("fecha_nacimiento");
  const fieldFoto = document.getElementById("foto_filename");
  const rutHint = document.getElementById("rut-hint");
  const edadHint = document.getElementById("edad-hint");

  let stream = null;

  function showError(msg) {
    cameraError.textContent = msg;
    cameraError.classList.remove("hidden");
  }

  function clearError() {
    cameraError.classList.add("hidden");
    cameraError.textContent = "";
  }

  async function startCamera() {
    clearError();
    preview.classList.add("hidden");
    video.classList.remove("hidden");
    captureGuide.classList.remove("hidden");
    btnCapture.classList.remove("hidden");
    btnRetake.classList.add("hidden");

    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 960 } },
        audio: false,
      });
      video.srcObject = stream;
    } catch (err) {
      showError(
        "No se pudo acceder a la cámara. Revisa los permisos del navegador o completa los datos manualmente."
      );
    }
  }

  function stopCamera() {
    if (stream) {
      stream.getTracks().forEach((t) => t.stop());
      stream = null;
    }
  }

  function validarRut(rutSucio) {
    if (!rutSucio) return false;
    const limpio = rutSucio.replace(/[.\s]/g, "").toUpperCase();
    const match = limpio.match(/^(\d{1,8})-([\dK])$/);
    if (!match) return false;
    const cuerpo = match[1];
    const dv = match[2];
    let suma = 0;
    let multiplo = 2;
    for (let i = cuerpo.length - 1; i >= 0; i--) {
      suma += parseInt(cuerpo[i], 10) * multiplo;
      multiplo = multiplo < 7 ? multiplo + 1 : 2;
    }
    const resto = 11 - (suma % 11);
    const dvEsperado = resto === 11 ? "0" : resto === 10 ? "K" : String(resto);
    return dvEsperado === dv;
  }

  function actualizarRutHint() {
    const valor = fieldRut.value.trim();
    if (!valor) {
      rutHint.textContent = "";
      rutHint.className = "field-hint";
      return;
    }
    if (validarRut(valor)) {
      rutHint.textContent = "RUT válido";
      rutHint.className = "field-hint ok";
    } else {
      rutHint.textContent = "RUT inválido, revísalo contra la foto";
      rutHint.className = "field-hint warn";
    }
  }

  function actualizarEdadHint() {
    const valor = fieldFecha.value;
    if (!valor) {
      edadHint.textContent = "";
      return;
    }
    const nacimiento = new Date(valor + "T00:00:00");
    if (isNaN(nacimiento.getTime())) {
      edadHint.textContent = "";
      return;
    }
    const hoy = new Date();
    let edad = hoy.getFullYear() - nacimiento.getFullYear();
    const aunNoCumple =
      hoy.getMonth() < nacimiento.getMonth() ||
      (hoy.getMonth() === nacimiento.getMonth() && hoy.getDate() < nacimiento.getDate());
    if (aunNoCumple) edad -= 1;

    if (edad < 0 || edad > 130) {
      edadHint.textContent = "Fecha de nacimiento fuera de rango";
      edadHint.className = "field-hint warn";
      return;
    }
    edadHint.className = "field-hint";
    edadHint.textContent = `${edad} años` + (edad < 60 ? " · no cumple el rango habitual de adulto mayor" : "");
  }

  function capturar() {
    const w = video.videoWidth;
    const h = video.videoHeight;
    if (!w || !h) return;
    canvas.width = w;
    canvas.height = h;
    canvas.getContext("2d").drawImage(video, 0, 0, w, h);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.85);

    preview.src = dataUrl;
    preview.classList.remove("hidden");
    video.classList.add("hidden");
    captureGuide.classList.add("hidden");
    btnCapture.classList.add("hidden");
    btnRetake.classList.remove("hidden");
    stopCamera();

    enviarAOcr(dataUrl);
  }

  async function enviarAOcr(dataUrl) {
    ocrStatus.textContent = "Leyendo documento…";
    ocrStatus.classList.remove("hidden");

    try {
      const resp = await fetch("/ocr", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image: dataUrl }),
      });
      const data = await resp.json();

      if (data.foto_filename) fieldFoto.value = data.foto_filename;

      if (data.error) {
        ocrStatus.textContent = data.error;
        return;
      }

      if (data.apellidos) fieldApellidos.value = data.apellidos;
      if (data.nombres) fieldNombres.value = data.nombres;
      if (data.rut) fieldRut.value = data.rut;
      if (data.fecha_nacimiento) fieldFecha.value = data.fecha_nacimiento;

      actualizarRutHint();
      actualizarEdadHint();

      ocrStatus.textContent = "Datos leídos automáticamente. Revísalos contra la foto antes de guardar.";
    } catch (err) {
      ocrStatus.textContent = "No se pudo contactar al servidor para leer el documento. Completa los datos a mano.";
    }
  }

  btnCapture.addEventListener("click", capturar);
  btnRetake.addEventListener("click", startCamera);
  fieldRut.addEventListener("input", actualizarRutHint);
  fieldFecha.addEventListener("input", actualizarEdadHint);

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    if (video.classList.contains("hidden")) return;
    const activo = document.activeElement;
    const estaEscribiendo = activo && ["INPUT", "TEXTAREA", "SELECT"].includes(activo.tagName);
    if (estaEscribiendo) return;
    e.preventDefault();
    capturar();
  });

  if (window.SACA_INITIAL_FOTO_URL) {
    preview.src = window.SACA_INITIAL_FOTO_URL;
    preview.classList.remove("hidden");
    video.classList.add("hidden");
    captureGuide.classList.add("hidden");
    btnCapture.classList.add("hidden");
    btnRetake.classList.remove("hidden");
  } else if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    startCamera();
  } else {
    showError("Este navegador no soporta acceso a la cámara. Completa los datos manualmente.");
  }

  actualizarRutHint();
  actualizarEdadHint();
})();
