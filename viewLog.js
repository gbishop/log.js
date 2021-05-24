window.addEventListener("load", () => {
  // scroll to the bottom on page load
  function scrollToBottom() {
    setTimeout(() => window.scrollTo(0, document.body.scrollHeight), 100);
  }

  async function fetchTable() {
    console.log("fetchTable");
    const form = new FormData(document.querySelector("form"));
    const queryParameters = new URLSearchParams(form).toString();
    const resp = await fetch(`/log?${queryParameters}`);
    const html = await resp.text();
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, "text/html");
    const table = document.querySelector("table");
    table.parentNode.replaceChild(doc.querySelector("table"), table);
    console.log("ends");
  }

  document.body.addEventListener("keydown", (ev) => {
    switch (ev.key) {
      case "End":
        console.log("End");
        ev.preventDefault();
        fetchTable().then(scrollToBottom());
        break;
      case "PageDown":
        console.log("PageDown");
        const body = document.body;
        console.log(window.scrollY, body.clientHeight);
        if (window.innerHeight + window.scrollY >= document.body.scrollHeight) {
          fetchTable();
        }
        break;
    }
  });

  document.body.addEventListener("keyup", (ev) => {
    switch (ev.key) {
      case "End":
        console.log("End up");
        ev.preventDefault();
        break;
    }
  });

  document.body.querySelector("form").addEventListener("change", fetchTable);
});
