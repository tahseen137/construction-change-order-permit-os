const loginForm = document.querySelector("#login-form");
const usernameField = document.querySelector("#username");
const passwordField = document.querySelector("#password");
const statusBanner = document.querySelector("#login-status");
const nextPathField = document.querySelector("#next-path");

function setStatus(message, tone = "info") {
  statusBanner.textContent = message;
  statusBanner.dataset.tone = tone;
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  try {
    setStatus("Signing in to your workspace...", "info");
    const response = await fetch("/api/session/login", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        username: usernameField.value,
        password: passwordField.value,
        next_path: nextPathField.value || "/",
      }),
    });

    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Unable to sign in");
    }

    window.location.assign(payload.next_path || "/");
  } catch (error) {
    setStatus(error.message, "error");
    usernameField.select();
  }
});
