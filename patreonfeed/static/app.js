// Filtering and "watched" marks. Everything is stored per browser in localStorage.

function load(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch (e) { return fallback; }
}
function store(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {}
}

const prefs = load("prefs", {});
const seen = new Set(load("seen", []));
const cards = [...document.querySelectorAll(".card")];
const chips = [...document.querySelectorAll("header .chip")];
const ytOnly = document.getElementById("yt");
const hideSeen = document.getElementById("unseen");

let feed = chips.some(c => c.dataset.c === prefs.feed) ? prefs.feed : "";
ytOnly.checked = prefs.yt !== false;
hideSeen.checked = !!prefs.unseen;

function apply() {
  store("prefs", { feed, yt: ytOnly.checked, unseen: hideSeen.checked });
  chips.forEach(c => c.classList.toggle("on", c.dataset.c === feed));
  cards.forEach(card => {
    const watched = seen.has(card.dataset.id);
    card.classList.toggle("seen", watched);
    card.classList.toggle("hide",
      (feed && card.dataset.feed !== feed) ||
      (ytOnly.checked && card.dataset.yt !== "1") ||
      (hideSeen.checked && watched));
  });
}

chips.forEach(chip => chip.addEventListener("click", () => { feed = chip.dataset.c; apply(); }));
ytOnly.addEventListener("change", apply);
hideSeen.addEventListener("change", apply);

cards.forEach(card => {
  card.addEventListener("click", () => {
    seen.add(card.dataset.id);
    store("seen", [...seen]);
    apply();
  });
  // Right-click a watched post to unmark it.
  card.addEventListener("contextmenu", ev => {
    if (!seen.has(card.dataset.id)) return;
    ev.preventDefault();
    seen.delete(card.dataset.id);
    store("seen", [...seen]);
    apply();
  });
});

apply();
