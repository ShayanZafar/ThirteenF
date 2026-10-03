/* Search suggestions as you type, for inputs marked data-suggest.
   data-suggest="open" opens the chosen stock's page; "fill" puts its CUSIP in
   the box and submits the form (adding it to the watchlist). Without
   JavaScript the forms still work as plain searches. */
(function () {
  "use strict";

  document.querySelectorAll("input[data-suggest]").forEach(setUp);

  function setUp(input) {
    var mode = input.getAttribute("data-suggest");
    var list = document.createElement("ul");
    list.id = input.id + "-suggestions";
    list.className = "app-suggest";
    list.setAttribute("role", "listbox");
    list.setAttribute("aria-label", "Matching stocks");
    list.hidden = true;

    var wrap = document.createElement("div");
    wrap.className = "app-suggest-wrap";
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);
    wrap.appendChild(list);

    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-controls", list.id);

    var items = [];
    var active = -1;
    var timer = null;
    var asked = 0;

    input.addEventListener("input", function () {
      clearTimeout(timer);
      var q = input.value.trim();
      if (!q) { close(); return; }
      timer = setTimeout(function () { ask(q); }, 120);
    });

    input.addEventListener("keydown", function (event) {
      if (list.hidden) return;
      if (event.key === "ArrowDown") { event.preventDefault(); move(1); }
      else if (event.key === "ArrowUp") { event.preventDefault(); move(-1); }
      else if (event.key === "Enter" && active >= 0) { event.preventDefault(); choose(items[active]); }
      else if (event.key === "Escape") { close(); }
    });

    input.addEventListener("blur", function () { setTimeout(close, 150); });

    function ask(q) {
      var mine = ++asked;
      fetch("/api/suggest?q=" + encodeURIComponent(q))
        .then(function (response) { return response.ok ? response.json() : []; })
        .then(function (found) {
          if (mine !== asked) return; // a newer keystroke has asked since
          items = found;
          render();
        })
        .catch(close);
    }

    function render() {
      list.textContent = "";
      active = -1;
      input.removeAttribute("aria-activedescendant");
      if (!items.length) { close(); return; }
      items.forEach(function (item, i) {
        var option = document.createElement("li");
        option.id = list.id + "-" + i;
        option.className = "app-suggest__item";
        option.setAttribute("role", "option");
        option.setAttribute("aria-selected", "false");
        if (item.ticker) {
          var ticker = document.createElement("span");
          ticker.className = "tf-ticker";
          ticker.textContent = item.ticker;
          option.appendChild(ticker);
        }
        var name = document.createElement("span");
        name.className = "app-suggest__name";
        name.textContent = item.name;
        option.appendChild(name);
        var funds = document.createElement("span");
        funds.className = "app-suggest__meta";
        funds.textContent = item.funds_text;
        option.appendChild(funds);
        option.addEventListener("mousedown", function (event) {
          event.preventDefault(); // keep focus in the box until the choice is made
          choose(item);
        });
        list.appendChild(option);
      });
      list.hidden = false;
      input.setAttribute("aria-expanded", "true");
    }

    function move(step) {
      active = (active + step + items.length) % items.length;
      Array.prototype.forEach.call(list.children, function (option, i) {
        option.setAttribute("aria-selected", i === active ? "true" : "false");
      });
      input.setAttribute("aria-activedescendant", list.id + "-" + active);
    }

    function choose(item) {
      close();
      if (mode === "fill") {
        input.value = item.cusip;
        if (input.form.requestSubmit) input.form.requestSubmit(); else input.form.submit();
      } else {
        window.location.href = "/stock/" + encodeURIComponent(item.cusip);
      }
    }

    function close() {
      list.hidden = true;
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
      active = -1;
    }
  }
})();
