import React, { useState, useRef, useEffect } from 'react';
import ParticleCloud from "./ParticleCloud";
import RecordingBars from "./RecordingBars";

// Add global declarations at the top of the file
declare global {
  interface Window {
    _audioController: { intercept: () => void } | null;
  }
}

// Initialize controller
if (typeof window !== 'undefined') {
  window._audioController = null;
}

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
  const playbackContextRef = useRef<AudioContext | null>(null);
  const playbackSourceRef = useRef<AudioBufferSourceNode | null>(null);
  const playbackAudioContextRef = useRef<AudioContext | null>(null);
  const playbackOscillatorRef = useRef<AudioScheduledSourceNode | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const isRecordingRef = useRef(false);
  const [barVolumes, setBarVolumes] = useState(Array(8).fill(0));
  const isTTSStoppedRef = useRef(false);
  const [audioKey, setAudioKey] = useState(0);

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
      hardStopAudio();
    };
    // eslint-disable-next-line
  }, []);

  const hardStopAudio = () => {
    console.log('Hard stopping all audio');

    // Use intercept method if available
    if (window._audioController) {
      try {
        window._audioController.intercept();
        window._audioController = null;
      } catch (e) {
        console.error('Error intercepting audio:', e);
      }
    }

    // Also stop any HTML audio playing through audio element
    if (audioPlayerRef.current) {
      try {
        const audio = audioPlayerRef.current;
        audio.onended = null; 
        audio.onerror = null;
        audio.onpause = null;
        audio.pause();
        audio.currentTime = 0;
        audio.src = '';
        audio.load();
      } catch (e) {
        console.log('Error stopping HTML audio:', e);
      }
    }

    // Make sure we're in the right state
    isTTSStoppedRef.current = true;
    console.log('All audio stopped');
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
  const INTERRUPT_THRESHOLD = 0.03; // Higher threshold for interruption to avoid false positives
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
        const rms = Math.sqrt(inputData.reduce((sum, sample) => sum + sample * sample, 0) / inputData.length);
        
        // Set bar volumes for visualization
        const bandSize = Math.floor(inputData.length / 8);
        const bands = Array(8).fill(0).map((_, i) => {
          const start = i * bandSize;
          const end = (i === 7) ? inputData.length : (i + 1) * bandSize;
          const band = inputData.slice(start, end);
          const bandRms = Math.sqrt(band.reduce((sum, s) => sum + s * s, 0) / band.length);
          return Math.min(1, bandRms * 10); // scale for visual effect
        });
        setBarVolumes(bands);

        // Interrupt TTS if speech detected
        if (status === 'speaking' && rms > INTERRUPT_THRESHOLD) {
          console.log('Interrupt condition met:', { status, rms });
          console.log(`INTERRUPT DETECT: Very strong speech detected (${rms.toFixed(4)}) during bot speech!`);
          if (audioPlayerRef.current) {
            try {
              console.log('Before pause:', {
                paused: audioPlayerRef.current.paused,
                currentTime: audioPlayerRef.current.currentTime,
                src: audioPlayerRef.current.src
              });
              audioPlayerRef.current.pause();
              audioPlayerRef.current.currentTime = 0;
              audioPlayerRef.current.src = '';
              audioPlayerRef.current.load();
              console.log('After pause:', {
                paused: audioPlayerRef.current.paused,
                currentTime: audioPlayerRef.current.currentTime,
                src: audioPlayerRef.current.src
              });
            } catch (e) { console.error('Error stopping audioPlayerRef on VAD interrupt:', e); }
          }
          setStatus('listening');
          stopListening();
          startRecording();
          return;
        }
        
        // Regular speech detection for starting recording
        if (rms > SPEECH_THRESHOLD) {
          speechBufferCount++;
          
          // If we have enough speech buffers, start recording
          if (speechBufferCount >= MIN_SPEECH_BUFFERS && !isRecordingRef.current) {
            console.log(`Starting recording after ${speechBufferCount} speech buffers`);
            setIsRecording(true);
            isRecordingRef.current = true;
            stopListening();
            startRecording();
            speechBufferCount = 0;
          } else if (status !== 'listening' && status !== 'processing') {
            setStatus('listening');
          }
        } else {
          speechBufferCount = 0;
        }
      };
    } catch (error) {
      console.error('Error accessing microphone:', error);
    }
  };

  const startRecording = () => {
    // Always stop TTS playback when recording starts
    if (audioPlayerRef.current) {
      try {
        console.log('Force stopping audioPlayerRef because recording is starting...');
        audioPlayerRef.current.pause();
        audioPlayerRef.current.currentTime = 0;
        audioPlayerRef.current.src = '';
        audioPlayerRef.current.load();
        console.log('AudioPlayerRef stopped due to recording start.');
      } catch (e) { console.error('Error stopping audioPlayerRef on recording start:', e); }
    }
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

  // Most aggressive audio stop possible
  const nuclearlySilenceAudio = () => {
    console.log('NUCLEAR OPTION: Forcefully silencing all audio');
    
    // 1. Try to stop any playing audio elements first (safely)
    try {
      document.querySelectorAll('audio').forEach(audio => {
        try {
          audio.pause();
          audio.currentTime = 0;
          audio.src = '';
          
          // Don't try to remove from DOM - that's React's job
          // if (audio.parentNode && !audio.hasAttribute('ref')) {
          //   audio.parentNode.removeChild(audio);
          // }
        } catch (e) {
          console.error('Error silencing audio:', e);
        }
      });
    } catch (e) {
      console.error('Error with document query:', e);
    }
    
    // 2. Kill our current audio reference
    if (audioPlayerRef.current) {
      try {
        audioPlayerRef.current.pause();
        audioPlayerRef.current.currentTime = 0;
        audioPlayerRef.current.src = '';
      } catch (e) {
        console.error('Error with audio ref:', e);
      }
    }
    
    // 3. Trigger remount of audio element by changing key
    setAudioKey(prev => prev + 1);
    
    // 4. Set the stopped flag
    isTTSStoppedRef.current = true;
    
    // 5. Try to use Web Audio API context closing as well
    if (typeof window !== 'undefined' && window._audioController) {
      try {
        window._audioController.intercept();
        window._audioController = null;
      } catch (e) {
        console.error('Error with audio controller:', e);
      }
    }
    
    // 6. Log success
    console.log('Audio should now be forcefully stopped');
  };

  // Utility: log every setStatus call with stack trace
  const setStatusWithLog = (newStatus: 'waiting' | 'listening' | 'speaking' | 'processing') => {
    if (status !== newStatus) {
      console.log(`setStatus called: ${status} -> ${newStatus}`);
      console.trace('setStatus stack trace');
    }
    setStatus(newStatus);
  };

  const playAudioResponse = (audioHex: string) => {
    setStatusWithLog('speaking');
    isTTSStoppedRef.current = false;
    console.log('Beginning TTS audio playback preparation...');
    console.log('TTS audioHex length:', audioHex.length);
    console.log('TTS audioHex sample (first 20 bytes):', audioHex.slice(0, 40));

    // Stop any previous playback
    if (audioPlayerRef.current) {
      try {
        console.log('Pausing and resetting audioPlayerRef due to new TTS playback...');
        audioPlayerRef.current.pause();
        audioPlayerRef.current.currentTime = 0;
        audioPlayerRef.current.src = '';
      } catch (e) { console.error('Error stopping previous audioPlayerRef:', e); }
    }

    try {
      // Convert hex to binary
      const binary = new Uint8Array(audioHex.match(/.{1,2}/g)!.map(byte => parseInt(byte, 16)));
      console.log('Binary length:', binary.length, 'First 20 bytes:', Array.from(binary.slice(0, 20)));
      const blob = new Blob([binary], { type: 'audio/wav' });
      const url = URL.createObjectURL(blob);
      if (audioPlayerRef.current) {
        audioPlayerRef.current.src = url;
        audioPlayerRef.current.onended = () => {
          console.log('TTS audio element ended.');
          setStatusWithLog('waiting');
          startListening();
          URL.revokeObjectURL(url);
        };
        audioPlayerRef.current.onerror = (e) => {
          console.error('TTS audio element error:', e);
          setStatusWithLog('waiting');
          startListening();
          URL.revokeObjectURL(url);
        };
        audioPlayerRef.current.play().then(() => {
          console.log('TTS audio element playback started.');
        }).catch(e => {
          console.error('TTS audio element playback failed:', e);
          setStatusWithLog('waiting');
          startListening();
          URL.revokeObjectURL(url);
        });
      } else {
        console.error('No audio player reference found');
        setStatusWithLog('waiting');
        startListening();
      }
    } catch (error) {
      console.error('Error in playAudioResponse:', error);
      setStatusWithLog('waiting');
      startListening();
    }
  };

  // Add logging for state transitions
  useEffect(() => {
    if (status === 'speaking') {
      console.log('Status changed to speaking: TTS playback should be active');
    } else {
      console.log('Status changed:', status);
    }
  }, [status]);

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
          {status === 'speaking' && <RecordingBars animate color="#e75480" key="speaking" />}
          {loading && status !== 'processing' && status !== 'listening' && status !== 'waiting' && status !== 'speaking' && <ParticleCloud />}
          <div className="text-center mt-4 text-gray-600">
            {status === 'waiting' && 'Waiting for Input...'}
            {status === 'listening' && 'Listening...'}
            {status === 'processing' && 'Processing your message...'}
            {status === 'speaking' && 'Bot is speaking...'}
          </div>
          <audio key={audioKey} ref={audioPlayerRef} className="hidden" />
        </div>
      </div>
    </div>
  );
}

export default App; 