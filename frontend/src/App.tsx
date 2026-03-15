/**
 * Copyright 2024 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import { useRef } from "react";
import "./App.scss";
import { LiveAPIProvider } from "./contexts/LiveAPIContext";
import SidePanel from "./components/side-panel/SidePanel";
import ControlTray from "./components/control-tray/ControlTray";
import { LiveClientOptions } from "./types";
import { TutorPanel } from "./components/tutor-panel/TutorPanel";

const apiOptions: LiveClientOptions = {
  apiBaseUrl: process.env.REACT_APP_API_BASE_URL,
  runtimeUrl: process.env.REACT_APP_RUNTIME_URL,
  websocketUrl: process.env.REACT_APP_LIVE_WS_URL,
  clientName: "ancient-greek-live-console",
  mode: "guided_reading",
  preferredResponseLanguage: "English",
};

function App() {
  const videoRef = useRef<HTMLVideoElement>(null);

  return (
    <div className="App">
      <LiveAPIProvider options={apiOptions}>
        <div className="streaming-console">
          <SidePanel />
          <main>
            <div className="main-app-area">
              <TutorPanel />
            </div>

            <ControlTray
              videoRef={videoRef}
              supportsAudio={false}
              supportsVideo={false}
              enableEditingSettings={false}
            >
              {/* put your own buttons here */}
            </ControlTray>
          </main>
        </div>
      </LiveAPIProvider>
    </div>
  );
}

export default App;
