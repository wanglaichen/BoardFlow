import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "@boardflow/editor-shell/styles.css";
import "./table.css";

createRoot(document.getElementById("root")).render(<App />);
