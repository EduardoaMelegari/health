const App = {
  async post(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error("Falha na requisição");
    return res.json();
  },

  fmt(n) {
    return Math.round(n).toLocaleString("pt-BR");
  },

  toggleTheme() {
    const root = document.documentElement;
    const current = root.dataset.theme
      || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = current === "dark" ? "light" : "dark";
    root.dataset.theme = next;
    localStorage.setItem("theme", next);
  },

  async toggleTask(el, templateId, date) {
    el.classList.toggle("done");
    try {
      const r = await this.post("/api/task/toggle", { template_id: templateId, date });
      el.classList.toggle("done", r.done);
    } catch {
      el.classList.toggle("done");
    }
  },

  async chooseMeal(el, mealId, optionId, date) {
    const card = el.closest("[data-meal]");
    const wasSelected = el.classList.contains("selected");
    card.querySelectorAll(".option").forEach((o) => o.classList.remove("selected"));
    if (!wasSelected) el.classList.add("selected");
    try {
      const r = await this.post("/api/meal/choose", { meal_id: mealId, option_id: optionId, date });
      card.querySelectorAll(".option").forEach((o) => o.classList.remove("selected"));
      if (r.chosen !== null) el.classList.add("selected");
      this.updateMacros(r.consumed, r.targets);
    } catch {
      el.classList.toggle("selected", wasSelected);
    }
  },

  updateMacros(consumed, targets) {
    const units = { kcal: " kcal", protein_g: " g", carbs_g: " g", fat_g: " g" };
    for (const key of Object.keys(units)) {
      const fill = document.querySelector(`[data-macro-fill="${key}"]`);
      const val = document.querySelector(`[data-macro-val="${key}"]`);
      if (!fill) continue;
      const pct = targets[key] ? (100 * consumed[key]) / targets[key] : 0;
      fill.style.width = Math.min(100, pct) + "%";
      fill.classList.toggle("over", pct > 107);
      val.textContent = `${this.fmt(consumed[key])} / ${this.fmt(targets[key])}${units[key]}`;
    }
    const note = document.getElementById("macro-note");
    if (!note) return;
    const missP = targets.protein_g - consumed.protein_g;
    const missK = targets.kcal - consumed.kcal;
    if (missP > 0) {
      note.className = "macro-note";
      note.innerHTML = `Faltam <strong>${this.fmt(missP)} g de proteína</strong> e ${this.fmt(Math.max(0, missK))} kcal para a meta.`;
    } else {
      note.className = "macro-note done";
      note.innerHTML = `<strong>Meta de proteína batida ✓</strong>` +
        (missK > 0 ? ` · restam ${this.fmt(missK)} kcal.` : ` · calorias no alvo.`);
    }
  },
};
