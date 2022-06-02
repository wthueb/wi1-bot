import { useEffect, useState } from "react";
import "./Log.css";

export default function Log() {
  const [command, setCommand] = useState("no command being run");
  const [log, setLog] = useState<string[]>([]);

  useEffect(() => {
    // const ws = new WebSocket("wss://ubuntu.wi1.xyz/ws");
    const ws = new WebSocket("ws://localhost:9001");

    ws.onmessage = function (ev) {
      const json = JSON.parse(ev.data);

      if (json.type === "log") {
        if (json.data.length === 0) {
          setCommand("no command being run");
          setLog([]);
          return;
        }

        setCommand(json.data[0]);
        setLog(json.data.slice(1));
      } else if (json.type === "update") {
        if (json.data.startsWith("$ ")) {
          setCommand(json.data);
          setLog([]);
        } else {
          setLog((l) => [...l, json.data]);
        }
      } else {
        console.log("unknown message", json);
      }
    };

    return () => ws.close();
  }, []);

  return (
    <div className="terminal">
      <div>
        <code>{command}</code>
        {log.map((entry, idx) => (
          <code key={idx}>{entry}</code>
        ))}
      </div>
    </div>
  );
}
