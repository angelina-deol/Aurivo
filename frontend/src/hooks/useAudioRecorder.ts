import { useCallback, useEffect, useRef, useState } from "react";

import { encodeWav, mergeFloat32Chunks } from "@/utils/wavEncoder";

export type RecorderStatus = "idle" | "recording" | "paused" | "stopped" | "error";

const LEVEL_BAR_COUNT = 32;
const BUFFER_SIZE = 4096;

/**
 * Records microphone audio and produces a real WAV Blob.
 *
 * Deliberately does NOT use MediaRecorder: its default output (webm/opus in
 * Chrome, ogg in Firefox) isn't one of the WAV/FLAC/MP3 formats the backend
 * accepts, and transcoding in the browser would need a heavy dependency
 * (ffmpeg.wasm). Instead this captures raw PCM via ScriptProcessorNode and
 * encodes a 16-bit WAV directly — small, dependency-free, and immediately
 * compatible with /investigations/analyze.
 *
 * ScriptProcessorNode is deprecated in favor of AudioWorklet, but remains
 * universally supported; worth revisiting if/when the app drops support for
 * older Safari versions.
 */
export function useAudioRecorder() {
  const [status, setStatus] = useState<RecorderStatus>("idle");
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [levels, setLevels] = useState<number[]>(Array(LEVEL_BAR_COUNT).fill(0.05));
  const [error, setError] = useState<string | null>(null);

  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Float32Array[]>([]);
  const isPausedRef = useRef(false);
  const rafRef = useRef<number | null>(null);
  const timerRef = useRef<number | null>(null);
  const sampleRateRef = useRef(44100);

  const cleanupMedia = useCallback(() => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    if (timerRef.current) window.clearInterval(timerRef.current);
    processorRef.current?.disconnect();
    sourceRef.current?.disconnect();
    analyserRef.current?.disconnect();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    audioContextRef.current?.close().catch(() => {});
    processorRef.current = null;
    sourceRef.current = null;
    analyserRef.current = null;
    audioContextRef.current = null;
    streamRef.current = null;
  }, []);

  useEffect(() => cleanupMedia, [cleanupMedia]);

  const tickLevels = useCallback(() => {
    const analyser = analyserRef.current;
    if (!analyser) return;

    const data = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteTimeDomainData(data);

    const chunkSize = Math.floor(data.length / LEVEL_BAR_COUNT) || 1;
    const nextLevels: number[] = [];
    for (let i = 0; i < LEVEL_BAR_COUNT; i++) {
      let peak = 0;
      for (let j = 0; j < chunkSize; j++) {
        const idx = i * chunkSize + j;
        if (idx >= data.length) break;
        const v = Math.abs(data[idx] - 128) / 128;
        if (v > peak) peak = v;
      }
      nextLevels.push(Math.max(0.05, peak));
    }
    setLevels(nextLevels);
    rafRef.current = requestAnimationFrame(tickLevels);
  }, []);

  const start = useCallback(async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const audioContext = new AudioContext();
      sampleRateRef.current = audioContext.sampleRate;
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;

      const processor = audioContext.createScriptProcessor(BUFFER_SIZE, 1, 1);
      chunksRef.current = [];
      isPausedRef.current = false;

      processor.onaudioprocess = (event) => {
        if (isPausedRef.current) return;
        const channelData = event.inputBuffer.getChannelData(0);
        chunksRef.current.push(new Float32Array(channelData));
      };

      source.connect(analyser);
      source.connect(processor);
      // ScriptProcessorNode only fires onaudioprocess while connected to a
      // destination — a muted gain would be cleaner, but connecting
      // straight to destination at zero cost here since we never route the
      // mic input to actual audio output.
      processor.connect(audioContext.destination);

      audioContextRef.current = audioContext;
      analyserRef.current = analyser;
      processorRef.current = processor;
      sourceRef.current = source;

      setElapsedSeconds(0);
      timerRef.current = window.setInterval(() => setElapsedSeconds((s) => s + 1), 1000);
      rafRef.current = requestAnimationFrame(tickLevels);
      setStatus("recording");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not access the microphone. Check your browser permissions."
      );
      setStatus("error");
    }
  }, [tickLevels]);

  const pause = useCallback(() => {
    isPausedRef.current = true;
    if (timerRef.current) window.clearInterval(timerRef.current);
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    setStatus("paused");
  }, []);

  const resume = useCallback(() => {
    isPausedRef.current = false;
    timerRef.current = window.setInterval(() => setElapsedSeconds((s) => s + 1), 1000);
    rafRef.current = requestAnimationFrame(tickLevels);
    setStatus("recording");
  }, [tickLevels]);

  const stop = useCallback((): Blob => {
    const merged = mergeFloat32Chunks(chunksRef.current);
    const wavBlob = encodeWav(merged, sampleRateRef.current);
    cleanupMedia();
    setStatus("stopped");
    return wavBlob;
  }, [cleanupMedia]);

  const cancel = useCallback(() => {
    cleanupMedia();
    chunksRef.current = [];
    setElapsedSeconds(0);
    setLevels(Array(LEVEL_BAR_COUNT).fill(0.05));
    setStatus("idle");
  }, [cleanupMedia]);

  return { status, elapsedSeconds, levels, error, start, pause, resume, stop, cancel };
}
