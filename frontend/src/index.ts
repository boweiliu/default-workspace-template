import m from "mithril";
import "./style.css";
import { initAgentManager } from "./models/AgentManager";
import { initHostPermissionResolutions } from "./views/permission-card";
import { App } from "./views/App";

function bootstrap(): void {
  initAgentManager();
  // Flip in-chat permission cards as soon as an embedding host reports a verdict.
  initHostPermissionResolutions();
  const rootElement = document.getElementById("app");
  if (rootElement) {
    m.mount(rootElement, App);
  }
}

window.addEventListener("load", bootstrap);
