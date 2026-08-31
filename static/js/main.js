// Generation screen. The backend is the same origin that serves the page, so
// requests use relative paths and the session travels in the cookie.

const MAX_LENGTH = 300;
const WARN_AT = 270;

const EXAMPLES = [
  "Create a customer feedback form",
  "Build a job application form",
  "Generate an event registration form",
  "Make a contact form with email validation",
  "Create a product order form",
];

document.addEventListener("DOMContentLoaded", () => {
  const input = document.getElementById("heroInput");
  const button = document.getElementById("sendButton");

  if (!input || !button) return;

  setupCharCounter(input, button);
  setupCopyButton();
  rotateSuggestions();

  button.addEventListener("click", () => createForm(input, button));

  input.addEventListener("keypress", (e) => {
    if (e.key === "Enter" && !input.disabled && !button.disabled) {
      e.preventDefault();
      createForm(input, button);
    }
  });
});


function setupCharCounter(input, button) {
  const counter = document.getElementById("charCounter");

  input.addEventListener("input", function () {
    const length = this.value.length;

    counter.textContent = `${length}/${MAX_LENGTH}`;
    counter.classList.toggle("text-warning", length > WARN_AT);
    counter.classList.toggle("text-secondary", length <= WARN_AT);

    setEnabled(button, length > 0 && !input.disabled);
  });
}


function setEnabled(button, enabled) {
  button.disabled = !enabled;
  button.style.opacity = enabled ? "1" : "0.5";
  button.style.cursor = enabled ? "pointer" : "not-allowed";
}


async function createForm(input, button) {
  const prompt = input.value.trim();
  if (!prompt) return;

  const resultBox = document.getElementById("resultBox");
  const loadingBox = document.getElementById("loadingBox");

  resultBox.classList.add("d-none");
  showLoading(loadingBox, "Creating your form...");

  setEnabled(button, false);
  button.innerText = "...";

  try {
    const res = await fetch("/create-form", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt: prompt,
        question_count: parseInt(document.getElementById("questionCount").value, 10),
        is_quiz: document.getElementById("isQuiz").checked,
      }),
    });

    const data = await res.json();

    if (!res.ok) {
      // Session expired: reloading lets the server send us to the login.
      if (res.status === 401) {
        window.location.reload();
        return;
      }
      showLoading(loadingBox, data.error || "Something went wrong.", true);
      return;
    }

    loadingBox.classList.add("d-none");
    showResult(resultBox, data);
    updateUsage(data.usage, input, button);

  } catch (error) {
    console.error(error);
    showLoading(loadingBox, "Error creating form. Please try again.", true);
  } finally {
    button.innerText = "→";
    if (!input.disabled) setEnabled(button, input.value.trim().length > 0);
  }
}


function showResult(resultBox, data) {
  document.getElementById("editButton").href = data.edit_url;
  document.getElementById("copyShareButton").dataset.url = data.share_url;
  resultBox.classList.remove("d-none");
}


// Reuses the same box for progress and for errors, hiding the spinner once the
// message is final.
function showLoading(loadingBox, message, isError = false) {
  loadingBox.classList.remove("d-none");

  const text = document.getElementById("loadingText");
  text.textContent = message;
  text.classList.toggle("text-danger", isError);
  text.classList.toggle("text-secondary", !isError);

  loadingBox.querySelector(".spinner-border").style.display = isError ? "none" : "";
}


function updateUsage(usage, input, button) {
  if (!usage) return;

  const display = document.getElementById("usageDisplay");

  if (usage.unlimited) {
    display.textContent = "Forms: Unlimited";
    return;
  }

  display.textContent = `Forms remaining: ${usage.remaining}/${usage.max}`;

  display.classList.remove("text-secondary", "text-warning", "text-danger");
  if (usage.remaining === 0) {
    display.classList.add("text-danger");
    input.disabled = true;
    input.placeholder = "No forms remaining.";
    setEnabled(button, false);
  } else {
    display.classList.add(usage.remaining <= 2 ? "text-warning" : "text-secondary");
  }
}


function setupCopyButton() {
  const button = document.getElementById("copyShareButton");

  button.addEventListener("click", async function () {
    this.blur();

    const url = this.dataset.url;
    if (!url) return;

    let copied = false;
    try {
      // Requires HTTPS or localhost; unavailable anywhere else.
      await navigator.clipboard.writeText(url);
      copied = true;
    } catch (error) {
      copied = copyFallback(url);
    }

    if (!copied) return;

    const original = this.textContent;
    this.classList.add("copied");
    this.textContent = "Copied!";

    setTimeout(() => {
      this.classList.remove("copied");
      this.textContent = original;
    }, 2000);
  });
}


function copyFallback(url) {
  const temp = document.createElement("input");
  temp.value = url;
  temp.style.cssText = "position:fixed;opacity:0;left:-9999px";

  document.body.appendChild(temp);
  temp.select();

  let success = false;
  try {
    success = document.execCommand("copy");
  } catch (error) {
    console.error("Copy failed:", error);
  }

  document.body.removeChild(temp);
  return success;
}


function rotateSuggestions() {
  const target = document.getElementById("suggestionText");
  let index = 0;

  const show = () => {
    target.style.opacity = 0;
    setTimeout(() => {
      target.textContent = EXAMPLES[index];
      target.style.opacity = 1;
      index = (index + 1) % EXAMPLES.length;
    }, 300);
  };

  show();
  setInterval(show, 3000);
}
