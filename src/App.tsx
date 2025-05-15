import React, { useState, useRef, useEffect } from 'react';
import ParticleCloud from "./ParticleCloud";
import RecordingBars from "./RecordingBars";

interface Message {
  role: 'user' | 'assistant';
  content: string;
  audio?: string;
  transcription?: string;
  files?: {
    original_audio: string;
    transcription: string;
    tts_audio: string;
  };
}

function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [status, setStatus] = useState<'waiting' | 'listening' | 'speaking' | 'processing'>('waiting');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const isRecordingRef = useRef(false);
  const [barVolumes, setBarVolumes] = useState(Array(8).fill(0));

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    // Start in waiting mode
    setStatus('waiting');
    startListening();
    // Cleanup on unmount
    return () => {
      stopListening();
      stopPlayback();
    };
    // eslint-disable-next-line
  }, []);

  const stopPlayback = () => {
    if (audioPlayerRef.current) {
      audioPlayerRef.current.pause();
      audioPlayerRef.current.currentTime = 0;
      audioPlayerRef.current.src = '';
      audioPlayerRef.current.onended = null;
    }
  };

  const stopListening = () => {
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current.onaudioprocess = null;
      processorRef.current = null;
    }
    if (sourceRef.current) {
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
  };

  const SPEECH_THRESHOLD = 0.02;
  const MIN_SPEECH_BUFFERS = 6; // ~250ms if buffer is ~46ms
  let speechBufferCount = 0;

  const startListening = async () => {
    setStatus('waiting');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
      audioContextRef.current = audioContext;
      const source = audioContext.createMediaStreamSource(stream);
      sourceRef.current = source;
      const processor = audioContext.createScriptProcessor(2048, 1, 1);
      processorRef.current = processor;
      source.connect(processor);
      processor.connect(audioContext.destination);

      speechBufferCount = 0;

      processor.onaudioprocess = (event) => {
        const inputData = event.inputBuffer.getChannelData(0);
        // Calculate RMS energy for VAD
        const rms = Math.sqrt(inputData.reduce((sum, sample) => sum + sample * sample, 0) / inputData.length);

        // Calculate 8 band volumes for animation
        const bandSize = Math.floor(inputData.length / 8);
        const bands = Array(8).fill(0).map((_, i) => {
          const start = i * bandSize;
          const end = (i === 7) ? inputData.length : (i + 1) * bandSize;
          const band = inputData.slice(start, end);
          const bandRms = Math.sqrt(band.reduce((sum, s) => sum + s * s, 0) / band.length);
          return Math.min(1, bandRms * 10); // scale for visual effect
        });
        setBarVolumes(bands);

        if (rms > SPEECH_THRESHOLD) {
          if (status !== 'listening') setStatus('listening');
          speechBufferCount += 1;
        } else {
          speechBufferCount = 0;
        }

        if (speechBufferCount >= MIN_SPEECH_BUFFERS && !isRecordingRef.current) {
          setIsRecording(true);
          isRecordingRef.current = true;
          stopListening();
          startRecording();
          speechBufferCount = 0; // reset after triggering
        }
      };
    } catch (error) {
      console.error('Error accessing microphone:', error);
    }
  };

  const startRecording = () => {
    stopListening(); // ensure all previous VAD is cleaned up
    setStatus('listening');
    setIsRecording(true);
    isRecordingRef.current = true;
    audioChunksRef.current = [];
    navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      mediaRecorder.ondataavailable = (event) => {
        audioChunksRef.current.push(event.data);
      };
      mediaRecorder.onstop = async () => {
        setStatus('processing');
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/wav' });
        await processAudio(audioBlob);
        setIsRecording(false); // unlock after recording
        isRecordingRef.current = false;
        setStatus('waiting'); // After processing, go back to waiting
        startListening();
      };
      mediaRecorder.start();
      setTimeout(() => {
        if (mediaRecorder.state === 'recording') {
          mediaRecorder.stop();
        }
      }, 5000); // Max 5 seconds per utterance
    });
  };

  const processAudio = async (audioBlob: Blob) => {
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('audio', audioBlob);
      const response = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        body: formData,
      });
      if (!response.ok) {
        throw new Error('Failed to process audio');
      }
      const data = await response.json();
      setMessages(prev => [...prev, 
        { role: 'user', content: data.transcription || 'Transcription not available', transcription: data.transcription, files: data.files },
        { role: 'assistant', content: data.response, audio: data.audio }
      ]);
      // Play the audio response
      if (data.audio) {
        playAudioResponse(data.audio);
      } else {
        // If no audio, resume listening
        startListening();
      }
    } catch (error) {
      console.error('Error processing audio:', error);
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: 'Sorry, there was an error processing your message.' 
      }]);
      startListening();
    } finally {
      setLoading(false);
    }
  };

  const playAudioResponse = (audioHex: string) => {
    setStatus('speaking');
    // Convert hex to binary
    const binary = new Uint8Array(audioHex.match(/.{1,2}/g)!.map(byte => parseInt(byte, 16)));
    const blob = new Blob([binary], { type: 'audio/wav' });
    const url = URL.createObjectURL(blob);

    if (audioPlayerRef.current) {
      // Stop and reset before playing new audio
      audioPlayerRef.current.pause();
      audioPlayerRef.current.currentTime = 0;
      audioPlayerRef.current.src = '';
      audioPlayerRef.current.onended = null;

      // Set new source and play
      audioPlayerRef.current.src = url;
      audioPlayerRef.current.play();
      audioPlayerRef.current.onended = () => {
        setStatus('waiting');
        startListening();
      };
    }
  };

  console.log("isRecording:", isRecording, "status:", status);

  return (
    <div className="min-h-screen bg-gray-100 flex flex-col">
      <div className="flex-1 container mx-auto px-4 py-8">
        <div className="bg-white rounded-lg shadow-lg p-6 h-[600px] flex flex-col">
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.map((message, index) => (
              <div
                key={index}
                className={`flex ${
                  message.role === 'user' ? 'justify-end' : 'justify-start'
                }`}
              >
                <div
                  className={`max-w-[70%] rounded-lg p-3 ${
                    message.role === 'user'
                      ? 'bg-blue-500 text-white'
                      : 'bg-gray-200 text-gray-800'
                  }`}
                >
                  {message.role === 'user' ? (
                    <p>{message.transcription || message.content}</p>
                  ) : (
                    <>
                      <p>{message.content}</p>
                      {message.transcription && (
                        <div className="mt-2 text-sm">
                          <p className="font-semibold">Transcription:</p>
                          <p className="italic">{message.transcription}</p>
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
          {status === 'waiting' && <RecordingBars animate color="purple" key="waiting" />}
          {status === 'listening' && <RecordingBars key="listening" volumes={barVolumes} color="purple" />}
          {status === 'processing' && <RecordingBars animate color="green" key="processing" />}
          {loading && status !== 'processing' && status !== 'listening' && status !== 'waiting' && <ParticleCloud />}
          <div className="text-center mt-4 text-gray-600">
            {status === 'waiting' && 'Waiting for Input...'}
            {status === 'listening' && 'Listening...'}
            {status === 'processing' && 'Processing your message...'}
            {status === 'speaking' && 'Bot is speaking...'}
          </div>
          <audio ref={audioPlayerRef} className="hidden" />
        </div>
      </div>
    </div>
  );
}

export default App; 