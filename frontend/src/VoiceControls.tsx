import { useRef, useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Mic, Square, Loader2, Volume2 } from "lucide-react";
import { api } from "./api";
import type { Health } from "./types";
export function VoiceControls({
  onTranscript,
}: {
  onTranscript: (s: string) => void;
}) {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api<Health>("/health"),
  });
  const recorder = useRef<MediaRecorder | null>(null),
    timer = useRef<ReturnType<typeof setTimeout>>(),
    [recording, setRecording] = useState(false),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  useEffect(
    () => () => {
      clearTimeout(timer.current);
      if (recorder.current?.state === "recording") recorder.current.stop();
    },
    [],
  );
  async function toggle() {
    if (recording) {
      recorder.current?.stop();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const media = new MediaRecorder(stream),
        chunks: BlobPart[] = [];
      recorder.current = media;
      media.ondataavailable = (e) => {
        if (e.data.size) chunks.push(e.data);
      };
      media.onstop = async () => {
        clearTimeout(timer.current);
        stream.getTracks().forEach((t) => t.stop());
        setRecording(false);
        setBusy(true);
        try {
          const form = new FormData();
          form.append(
            "file",
            new Blob(chunks, { type: media.mimeType }),
            "recording.webm",
          );
          const result = await api<{ text: string }>("/voice/asr", {
            method: "POST",
            body: form,
          });
          onTranscript(result.text);
          setMessage("识别已填入输入框，请核对日期和金额后再发送。");
        } catch (e) {
          setMessage((e as Error).message);
        } finally {
          setBusy(false);
        }
      };
      media.start();
      setRecording(true);
      setMessage("录音中，最多 60 秒。点击停止后识别。");
      timer.current = setTimeout(() => media.stop(), 60000);
    } catch {
      setMessage("无法使用麦克风，请检查浏览器权限与安全连接。");
    }
  }
  if (!health.data?.voice_enabled) return null;
  return (
    <div className="voice-controls">
      <button type="button" disabled={busy} onClick={toggle}>
        {busy ? (
          <Loader2 size={13} className="spin" />
        ) : recording ? (
          <Square size={13} />
        ) : (
          <Mic size={13} />
        )}{" "}
        {recording ? "停止并识别" : "语音输入"}
      </button>
      {message && <small>{message}</small>}
    </div>
  );
}
