import { useRef, useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Mic, Square, Loader2 } from "lucide-react";
import { api } from "./api";
import type { Health } from "./types";

type Props = {
  onTranscript: (s: string) => void;
  disabled?: boolean;
};

/** 语音只负责「说话 → 文本」；转写结果必须经用户确认后由同一个 send() 入口提交。 */
export function VoiceControls({ onTranscript, disabled = false }: Props) {
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
  const enabled = health.data?.voice_enabled === true;
  const ready = health.data?.voice_ready === true;
  const hint = !enabled
    ? "语音识别未启用 · 需配置 voice_enabled 与 ASR Key"
    : "缺少语音服务凭证 · 请填写 voice_api_key";

  async function toggle() {
    if (recording) {
      recorder.current?.stop();
      return;
    }
    setMessage("");
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
        if (!chunks.length) {
          setMessage("没有录到音频，请检查麦克风权限后重试。");
          return;
        }
        setBusy(true);
        try {
          const form = new FormData();
          form.append(
            "file",
            new Blob(chunks, { type: media.mimeType || "audio/webm" }),
            "recording.webm",
          );
          const result = await api<{ text: string; requires_confirmation?: boolean }>(
            "/voice/asr",
            { method: "POST", body: form },
          );
          const text = (result.text || "").trim();
          if (!text) {
            setMessage("未识别到可辨认的语音内容，请重试。");
            return;
          }
          onTranscript(text);
          setMessage("识别文本已填入输入框，请核对日期和金额后再发送。");
        } catch (e) {
          setMessage((e as Error).message);
        } finally {
          setBusy(false);
        }
      };
      media.start();
      setRecording(true);
      setMessage("录音中，最多 60 秒；点击停止后识别。");
      timer.current = setTimeout(() => {
        if (media.state === "recording") media.stop();
      }, 60000);
    } catch {
      setMessage("无法使用麦克风，请检查浏览器权限与安全连接。");
    }
  }

  if (health.isLoading) return null;
  if (health.isError) {
    return (
      <div className="voice-controls">
        <small role="status">语音状态暂不可用，请检查服务连接。</small>
      </div>
    );
  }
  if (!ready) {
    return (
      <div className="voice-controls">
        <button type="button" disabled aria-label="语音输入不可用">
          <Mic size={13} /> 语音输入
        </button>
        <small role="status">{hint}</small>
      </div>
    );
  }
  return (
    <div className="voice-controls">
      <button
        type="button"
        disabled={busy || (disabled && !recording)}
        aria-label={recording ? "停止录音并识别" : "开始语音输入"}
        onClick={toggle}
      >
        {busy ? (
          <Loader2 size={13} className="spin" />
        ) : recording ? (
          <Square size={13} />
        ) : (
          <Mic size={13} />
        )}{" "}
        {recording ? "停止并识别" : "语音输入"}
      </button>
      {message && (
        <small role="status" aria-live="polite">
          {message}
        </small>
      )}
    </div>
  );
}
