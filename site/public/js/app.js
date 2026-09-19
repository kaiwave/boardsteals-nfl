(function () {
  "use strict";

  var PAGE_SIZE = 8;
  var POSITION_ORDER = ["QB", "RB", "WR", "TE", "FB", "K"];

  var state = {
    players: [],
    filtered: [],
    filter: "ALL",
    visible: PAGE_SIZE,
  };

  var els = {
    seasonBadge: document.getElementById("seasonBadge"),
    statusLine: document.getElementById("statusLine"),
    filters: document.getElementById("filters"),
    grid: document.getElementById("grid"),
    loadMoreBtn: document.getElementById("loadMoreBtn"),
    exhaustedMsg: document.getElementById("exhaustedMsg"),
    cardTemplate: document.getElementById("cardTemplate"),
  };

  function tierFor(rating) {
    if (rating >= 98) return { key: "diamond", label: "Diamond" };
    if (rating >= 81) return { key: "gold", label: "Gold" };
    if (rating >= 71) return { key: "silver", label: "Silver" };
    if (rating >= 56) return { key: "bronze", label: "Bronze" };
    return { key: "iron", label: "Iron" };
  }

  function headshotSrc(player) {
    if (player.headshot) return player.headshot.replace(/^\//, "");
    return "assets/headshots/" + player.id + ".png";
  }

  function logoSrc(player) {
    var team = (player.team || "").toUpperCase();
    return "assets/logos/" + team + ".png";
  }

  function fmt1(n) {
    return typeof n === "number" ? n.toFixed(1) : "—";
  }

  function fmt2(n) {
    return typeof n === "number" ? n.toFixed(2) : "—";
  }

  function orderedPositions(players) {
    var present = {};
    players.forEach(function (p) { present[p.position] = true; });
    var ordered = POSITION_ORDER.filter(function (pos) { return present[pos]; });
    Object.keys(present).forEach(function (pos) {
      if (ordered.indexOf(pos) === -1) ordered.push(pos);
    });
    return ordered;
  }

  function buildFilters() {
    var positions = orderedPositions(state.players);
    els.filters.innerHTML = "";

    var all = [{ key: "ALL", label: "All" }].concat(
      positions.map(function (pos) { return { key: pos, label: pos }; })
    );

    all.forEach(function (item) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "pill";
      btn.textContent = item.label;
      btn.dataset.pos = item.key;
      btn.setAttribute("aria-pressed", String(item.key === state.filter));
      btn.addEventListener("click", function () {
        state.filter = item.key;
        state.visible = PAGE_SIZE;
        Array.prototype.forEach.call(els.filters.children, function (child) {
          child.setAttribute("aria-pressed", String(child.dataset.pos === state.filter));
        });
        applyFilter();
        render();
      });
      els.filters.appendChild(btn);
    });
  }

  function applyFilter() {
    state.filtered =
      state.filter === "ALL"
        ? state.players
        : state.players.filter(function (p) { return p.position === state.filter; });

    setStatus();
  }

  function buildCard(player, rank) {
    var node = els.cardTemplate.content.cloneNode(true);
    var article = node.querySelector(".card");
    var tier = tierFor(player.rating);
    article.dataset.tier = tier.key;

    node.querySelector(".rank").textContent = "#" + (player.rank || rank);

    var headshot = node.querySelector(".headshot");
    headshot.src = headshotSrc(player);
    headshot.alt = player.name;
    headshot.onerror = function () {
      headshot.onerror = null;
      headshot.src = "assets/headshots/placeholder.svg";
    };

    var logo = node.querySelector(".team-logo");
    logo.src = logoSrc(player);
    logo.alt = (player.team || "") + " logo";
    logo.onerror = function () {
      logo.onerror = null;
      logo.src = "assets/logos/placeholder.svg";
    };

    node.querySelector(".player-name").textContent = player.name;
    node.querySelector(".player-meta").textContent = player.position + ", " + player.team;

    node.querySelector(".rating-value").textContent = fmt1(player.rating);
    node.querySelector(".tier-label").textContent = tier.label;

    var main = player.main_stats || {};
    node.querySelector(".stat-expected").textContent = fmt1(main.expected_points);
    node.querySelector(".stat-actual").textContent = fmt1(main.actual_points);
    node.querySelector(".stat-opp").textContent =
      typeof main.total_opportunity === "number" ? main.total_opportunity : "—";

    var detailList = node.querySelector(".detail-stats");
    detailList.innerHTML = ""; // Ensure it's clean
    
    var detailArray = player.detail_stats || [];
    
    detailArray.forEach(function (stat) {
      var div = document.createElement("div");
      
      var dt = document.createElement("dt");
      dt.textContent = stat.label;
      
      var dd = document.createElement("dd");
      dd.textContent = stat.value != null ? stat.value : "—";
      
      div.appendChild(dt);
      div.appendChild(dd);
      detailList.appendChild(div);
    });
    
    return node;
}

  function render() {
    els.grid.innerHTML = "";

    if (state.filtered.length === 0) {
      var empty = document.createElement("p");
      empty.className = "empty-state";
      empty.textContent = "No players at this position this week.";
      els.grid.appendChild(empty);
      els.loadMoreBtn.hidden = true;
      els.exhaustedMsg.hidden = true;
      return;
    }

    var slice = state.filtered.slice(0, state.visible);
    slice.forEach(function (player, i) {
      els.grid.appendChild(buildCard(player, i + 1));
    });

    var remaining = state.filtered.length - state.visible;
    if (remaining > 0) {
      els.loadMoreBtn.hidden = false;
      els.exhaustedMsg.hidden = true;
      els.loadMoreBtn.textContent =
        "Show " + Math.min(PAGE_SIZE, remaining) + " more";
    } else {
      els.loadMoreBtn.hidden = true;
      els.exhaustedMsg.hidden = false;
      els.exhaustedMsg.textContent =
        state.filtered.length >= 50
          ? "That's the bottom of the board (all 50 shown)."
          : "All " + state.filtered.length + " players shown for this position.";
    }
  }

  els.loadMoreBtn.addEventListener("click", function () {
    state.visible += PAGE_SIZE;
    render();
  });

 function setStatus() {
    var meta = state.meta || {};
    var mode = state.mode;
    var count = (state.filtered ? state.filtered.length : state.players.length) || 0;
    var pos = (state.filter && state.filter !== "ALL") ? state.filter + "s" : "players";

    if (mode === "weekly") {
      els.seasonBadge.textContent = (meta.season || "") + " Season | Week " + (meta.current_week || "");
      els.statusLine.textContent =
        "The " + count + " most underrated " + pos + " from week " + (meta.current_week || "") + ".";
    } else {
      els.seasonBadge.textContent = (meta.season || "") + " season closed";
      els.statusLine.textContent =
        "Season's over, here were the top " +
        count +
        " " +
        pos +
        " by Boardsteals rating from the " +
        (meta.last_completed_season || "") +
        " season.";
    }
  }

  function fetchJson(path) {
    return fetch(path).then(function (res) {
      if (!res.ok) throw new Error("Failed to load " + path);
      return res.json();
    });
  }

  function init() {
    fetchJson("data/picks_weekly.json")
      .then(function (weekly) {
        if (weekly.meta && weekly.meta.is_season_active) {
          return { payload: weekly, mode: "weekly" };
        }
        return fetchJson("data/picks_global.json").then(function (global) {
          return { payload: global, mode: "global" };
        });
      })
      .then(function (result) {
        state.meta = result.payload.meta || {};
        state.mode = result.mode;
        state.players = result.payload.players || [];
        state.filtered = state.players;

        state.players.forEach(function (player, index) {
            player.rank = index + 1;
        });
        
        state.filtered = state.players;

        buildFilters();
        applyFilter();
        render();
      })
      .catch(function (err) {
        els.seasonBadge.textContent = "Unavailable";
        els.statusLine.textContent = "Couldn't load this week's board. Try refreshing in a bit.";
        els.loadMoreBtn.hidden = true;
        console.error(err);
      });
  }

  init();
})();
