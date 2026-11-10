// teach quiz component. Copy into the workspace's ./assets/ and link it from every lesson.
// It shuffles answers when the page renders, so the correct answer cannot sit in one slot
// (upstream issue #335: wording-only fixes left it in slot A 33 times out of 33).
//
// Markup it upgrades:
//   <div class="quiz" data-correct="0">
//     <p class="q">Question text</p>
//     <button>Correct answer</button><button>Wrong</button><button>Wrong</button>
//     <p class="feedback" hidden></p>
//   </div>
// Author the correct answer FIRST and set data-correct="0"; the shuffle moves it.
(function (root) {
  function shuffleOptions(options, correctIndex) {
    const order = options.map((_, i) => i);
    for (let i = order.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [order[i], order[j]] = [order[j], order[i]];
    }
    return { options: order.map((i) => options[i]), correctIndex: order.indexOf(correctIndex) };
  }

  function mount(el) {
    const buttons = Array.from(el.querySelectorAll("button"));
    const feedback = el.querySelector(".feedback");
    const { options, correctIndex } = shuffleOptions(buttons.map((b) => b.innerHTML), Number(el.dataset.correct || 0));
    buttons.forEach((b, i) => {
      b.innerHTML = options[i];
      b.addEventListener("click", () => {
        const right = i === correctIndex;
        b.classList.add(right ? "right" : "wrong");
        if (feedback) {
          feedback.hidden = false;
          feedback.textContent = right ? "Correct." : "Not quite. Try again before reading on.";
        }
      });
    });
  }

  root.TeachQuiz = { shuffleOptions, mount };
  if (root.document) root.document.addEventListener("DOMContentLoaded", () => root.document.querySelectorAll(".quiz").forEach(mount));
})(typeof window !== "undefined" ? window : globalThis);
