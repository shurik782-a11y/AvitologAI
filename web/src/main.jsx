import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./styles.css";

const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
  document.documentElement.dataset.theme = tg.colorScheme || "light";
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
