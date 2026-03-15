import "./logger.scss";

import cn from "classnames";
import { memo, ReactNode } from "react";
import { useLoggerStore } from "../../lib/store-logger";
import SyntaxHighlighter from "react-syntax-highlighter";
import { vs2015 as dark } from "react-syntax-highlighter/dist/esm/styles/hljs";
import {
  BackendEventLog,
  ClientContentLog as ClientContentLogType,
  StreamingLog,
} from "../../types";

const formatTime = (d: Date) => d.toLocaleTimeString().slice(0, -3);

const isClientContentLog = (
  message: StreamingLog["message"]
): message is ClientContentLogType =>
  typeof message === "object" &&
  message !== null &&
  "turns" in message &&
  "turnComplete" in message;

const isBackendEventLog = (
  message: StreamingLog["message"]
): message is BackendEventLog =>
  typeof message === "object" &&
  message !== null &&
  "eventType" in message &&
  "payload" in message;

const LogEntry = memo(
  ({
    log,
    MessageComponent,
  }: {
    log: StreamingLog;
    MessageComponent: ({
      message,
    }: {
      message: StreamingLog["message"];
    }) => ReactNode;
  }): JSX.Element => (
    <li
      className={cn(
        "plain-log",
        `source-${log.type.includes(".") ? log.type.split(".")[0] : "misc"}`,
        {
          receive: log.type.includes("receive"),
          send: log.type.includes("send"),
        }
      )}
    >
      <span className="timestamp">{formatTime(log.date)}</span>
      <span className="source">{log.type}</span>
      <span className="message">
        <MessageComponent message={log.message} />
      </span>
      {log.count && <span className="count">{log.count}</span>}
    </li>
  )
);

const PlainTextMessage = ({
  message,
}: {
  message: StreamingLog["message"];
}) => <span>{message as string}</span>;

const JsonMessage = ({
  message,
}: {
  message: StreamingLog["message"];
}) => (
  <SyntaxHighlighter language="json" style={dark}>
    {JSON.stringify(message, null, "  ")}
  </SyntaxHighlighter>
);

const ClientContentLog = memo(({ message }: { message: StreamingLog["message"] }) => {
  const { turns, turnComplete } = message as ClientContentLogType;
  const textParts = turns.filter((part) => part.text && part.text.trim().length > 0);

  return (
    <div className="rich-log client-content user">
      <h4 className="roler-user">Learner</h4>
      <div>
        {textParts.map((part, index) => (
          <p className="part part-text" key={`message-part-${index}`}>
            {part.text}
          </p>
        ))}
      </div>
      {!turnComplete ? <span>turnComplete: false</span> : null}
    </div>
  );
});

const BackendEventMessage = memo(
  ({ message }: { message: StreamingLog["message"] }) => {
    const { payload } = message as BackendEventLog;

    switch (payload.type) {
      case "server.transcript": {
        const transcriptPayload = payload as {
          speaker: string;
          text: string;
        };
        return (
          <div className={`rich-log model-turn ${transcriptPayload.speaker}`}>
            <h4>{transcriptPayload.speaker}</h4>
            <p>{transcriptPayload.text}</p>
          </div>
        );
      }
      case "server.status":
        return <span>{`${payload.phase}: ${payload.detail}`}</span>;
      case "server.tool.call":
        return <span>{`tool ${payload.tool_name} requested`}</span>;
      case "server.tool.result":
        return (
          <span>{`tool ${payload.tool_name} ${payload.status}`}</span>
        );
      case "server.error":
        return <span>{`${payload.code}: ${payload.message}`}</span>;
      case "server.turn": {
        const turnPayload = payload as {
          detail?: string | null;
          event: string;
        };
        return <span>{turnPayload.detail || turnPayload.event}</span>;
      }
      default:
        return <JsonMessage message={payload} />;
    }
  }
);

export type LoggerFilterType = "conversations" | "tools" | "none";

export type LoggerProps = {
  filter: LoggerFilterType;
};

const filters: Record<LoggerFilterType, (log: StreamingLog) => boolean> = {
  tools: (log: StreamingLog) =>
    isBackendEventLog(log.message) &&
    (log.message.payload.type === "server.tool.call" ||
      log.message.payload.type === "server.tool.result"),
  conversations: (log: StreamingLog) =>
    isClientContentLog(log.message) ||
    (isBackendEventLog(log.message) &&
      (log.message.payload.type === "server.transcript" ||
        log.message.payload.type === "server.status" ||
        log.message.payload.type === "server.turn" ||
        log.message.payload.type === "server.error")),
  none: () => true,
};

const component = (log: StreamingLog) => {
  if (typeof log.message === "string") {
    return PlainTextMessage;
  }
  if (isClientContentLog(log.message)) {
    return ClientContentLog;
  }
  if (isBackendEventLog(log.message)) {
    return BackendEventMessage;
  }
  return JsonMessage;
};

export default function Logger({ filter = "none" }: LoggerProps) {
  const { logs } = useLoggerStore();
  const filterFn = filters[filter];

  return (
    <div className="logger">
      <ul className="logger-list">
        {logs.filter(filterFn).map((log, key) => (
          <LogEntry MessageComponent={component(log)} log={log} key={key} />
        ))}
      </ul>
    </div>
  );
}
