// odswiezanie czatu co 5 s (polling), bez WebSocketow
(function () {
  const box = document.getElementById("chat-messages");
  if (!box) return;
  const url = box.dataset.url;
  const scrollDown = () => { box.scrollTop = box.scrollHeight; };
  scrollDown();

  setInterval(async () => {
    try {
      const resp = await fetch(url, { credentials: "same-origin" });
      // przekierowanie = sesja wygasla, nie wklejamy strony logowania do czatu
      if (!resp.ok || resp.redirected) return;
      const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
      box.innerHTML = await resp.text();  // HTML z serwera, juz escapowany przez Django
      if (atBottom) scrollDown();
    } catch (e) {
      // brak sieci - sprobujemy za chwile
    }
  }, 5000);
})();

