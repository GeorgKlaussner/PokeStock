(function () {
  const root = document.querySelector("[data-camera-add]");
  if (!root) {
    return;
  }

  const fileInput = document.getElementById("camera-input");
  const processButton = document.getElementById("camera-process");
  const preview = document.getElementById("camera-preview");
  const status = document.getElementById("camera-status");
  const textOutput = document.getElementById("camera-text");
  const candidatesRoot = document.getElementById("camera-candidates");
  const emptyMessage = document.getElementById("camera-empty");
  const manualLink = document.getElementById("camera-manual-link");
  const csrfToken = root.querySelector("[name=csrfmiddlewaretoken]").value;
  const candidatesUrl = root.dataset.candidatesUrl;
  let previewUrl = "";

  fileInput.addEventListener("change", () => {
    clearResults();
    processButton.disabled = !fileInput.files.length;
    status.textContent = fileInput.files.length ? "Ready to read this photo." : "Choose a photo to start.";
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      previewUrl = "";
    }
    if (fileInput.files.length) {
      previewUrl = URL.createObjectURL(fileInput.files[0]);
      preview.src = previewUrl;
      preview.hidden = false;
    } else {
      preview.hidden = true;
      preview.removeAttribute("src");
    }
  });

  processButton.addEventListener("click", async () => {
    const file = fileInput.files[0];
    if (!file) {
      return;
    }

    processButton.disabled = true;
    status.textContent = "Reading card text in this browser...";
    clearResults();

    try {
      if (!window.Tesseract) {
        throw new Error("OCR library did not load.");
      }
      const result = await window.Tesseract.recognize(file, "eng", {
        logger: (message) => {
          if (message.status === "recognizing text" && message.progress) {
            status.textContent = `Reading text ${Math.round(message.progress * 100)}%`;
          }
        },
      });
      const text = (result.data.text || "").trim();
      textOutput.textContent = text || "No text was recognized.";
      textOutput.hidden = false;
      clearImageInput();

      if (!text) {
        status.textContent = "No text was recognized. Try a sharper, brighter photo.";
        return;
      }

      status.textContent = "Searching PokemonTCG...";
      const response = await fetch(candidatesUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ text }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Card matching failed.");
      }
      renderCandidates(payload);
    } catch (error) {
      status.textContent = error.message;
    } finally {
      processButton.disabled = !fileInput.files.length;
    }
  });

  function clearImageInput() {
    fileInput.value = "";
    processButton.disabled = true;
    preview.hidden = true;
    preview.removeAttribute("src");
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      previewUrl = "";
    }
  }

  function clearResults() {
    candidatesRoot.replaceChildren();
    emptyMessage.hidden = true;
    manualLink.hidden = true;
  }

  function renderCandidates(payload) {
    clearResults();
    if (payload.manual_search_url) {
      manualLink.href = payload.manual_search_url;
      manualLink.hidden = false;
    }
    const candidates = payload.candidates || [];
    if (!candidates.length) {
      emptyMessage.hidden = false;
      status.textContent = "No likely matches found.";
      return;
    }
    status.textContent = `${candidates.length} likely match${candidates.length === 1 ? "" : "es"} found.`;
    for (const candidate of candidates) {
      candidatesRoot.appendChild(candidateCard(candidate));
    }
  }

  function candidateCard(candidate) {
    const article = document.createElement("article");
    article.className = "card candidate";

    if (candidate.image_url) {
      const image = document.createElement("img");
      image.src = candidate.image_url;
      image.alt = candidate.name;
      article.appendChild(image);
    }

    const body = document.createElement("div");
    const title = document.createElement("h2");
    title.textContent = candidate.name;
    body.appendChild(title);

    const meta = document.createElement("p");
    meta.className = "subtle";
    meta.textContent = `${candidate.set_name} #${candidate.card_number}${candidate.rarity ? ` - ${candidate.rarity}` : ""}`;
    body.appendChild(meta);

    const price = document.createElement("p");
    price.textContent = candidate.price ? `${candidate.price} ${candidate.currency}` : "Price unavailable";
    body.appendChild(price);
    article.appendChild(body);

    const actions = document.createElement("div");
    actions.className = "actions";

    const form = document.createElement("form");
    form.method = "post";
    form.action = candidate.quick_add_url;
    const csrf = document.createElement("input");
    csrf.type = "hidden";
    csrf.name = "csrfmiddlewaretoken";
    csrf.value = csrfToken;
    form.appendChild(csrf);
    const addButton = document.createElement("button");
    addButton.type = "submit";
    addButton.textContent = "Quick add";
    form.appendChild(addButton);
    actions.appendChild(form);

    const editLink = document.createElement("a");
    editLink.className = "button secondary";
    editLink.href = candidate.edit_url;
    editLink.textContent = "Edit details";
    actions.appendChild(editLink);
    article.appendChild(actions);

    return article;
  }
})();

