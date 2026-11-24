(() => {
  'use strict';

  let dailyScript;
  function loadDaily() {
    if (!dailyScript) {
      dailyScript = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/@daily-co/daily-js@0.95.0/dist/daily.js';
        script.integrity = 'sha384-msLrigBS7qFvKNKkcY8NqTkfiQqYvj7h70XNgRJmxhUhmwx2RvQ5xehvzUwpdH/2';
        script.crossOrigin = 'anonymous';
        script.onload = () => window.Daily?.createCallObject
          ? resolve(window.Daily)
          : reject(new Error('Video playback is unavailable'));
        script.onerror = () => reject(new Error('Video playback is unavailable'));
        document.head.append(script);
      });
    }
    return dailyScript;
  }

  function play({ api, interviewId, question, video, onSpeaking }) {
    const connection = new AbortController();
    let room;
    let call;
    let disposed = false;
    const videoBox = video.closest('.hr-interviewer-frame');
    const clearVideo = () => {
      video.muted = true;
      video.pause();
      video.srcObject = null;
      videoBox.classList.remove('has-live-avatar');
    };
    const endRoom = () => {
      if (!room) return;
      void api('/mock-interview/live/end', {
        method: 'POST',
        keepalive: true,
        body: JSON.stringify({
          conversation_id: room.conversation_id,
          session_proof: room.session_proof,
        }),
      }).catch(() => {});
    };
    const close = () => {
      if (disposed) return;
      disposed = true;
      connection.abort();
      clearVideo();
      if (call) void call.destroy().catch(() => {});
      endRoom();
    };

    const finished = (async () => {
      const daily = await Promise.race([
        loadDaily(),
        new Promise((_, reject) => setTimeout(() => reject(new Error('Video player timed out')), 3500)),
      ]);
      connection.signal.throwIfAborted();
      room = await api(`/mock-interview/live/assessment/${encodeURIComponent(interviewId)}/questions/${question.question_id}`, {
        method: 'POST',
        signal: AbortSignal.timeout(8000),
      });
      if (disposed) {
        // A manual skip may arrive while the server is creating the room.
        endRoom();
        return;
      }

      call = daily.createCallObject({ audioSource: false, videoSource: false, startAudioOff: true, startVideoOff: true });
      await new Promise((resolve, reject) => {
        let participantId;
        let spoke = false;
        let settled = false;
        const inferenceId = crypto.randomUUID();
        let timeout = setTimeout(() => finish(new Error('Video playback timed out')), 10000);
        const aborted = () => finish(new DOMException('Playback cancelled', 'AbortError'));

        function finish(error) {
          if (settled) return;
          settled = true;
          clearTimeout(timeout);
          connection.signal.removeEventListener('abort', aborted);
          call.off('participant-joined', onParticipant);
          call.off('participant-updated', onParticipant);
          call.off('app-message', onMessage);
          video.muted = true;
          onSpeaking(false);
          if (error) reject(error);
          else resolve();
        }

        function onMessage(event) {
          const message = event.data;
          if (event.fromId !== participantId ||
              (message?.conversation_id && message.conversation_id !== room.conversation_id) ||
              (message?.inference_id && message.inference_id !== inferenceId) ||
              !['pal', 'replica'].includes(message?.properties?.role)) return;
          if (message.event_type === 'conversation.started_speaking') {
            if (spoke) return;
            spoke = true;
            clearTimeout(timeout);
            timeout = setTimeout(() => finish(new Error('Video playback timed out')), 60000);
            onSpeaking(true);
          }
          if (spoke && message.event_type === 'conversation.stopped_speaking') {
            finish(message.properties.interrupted ? new Error('Video playback was interrupted') : null);
          }
        }

        function onParticipant({ participant }) {
          if (settled || participantId || !participant || participant.local) return;
          const audio = participant.tracks?.audio?.persistentTrack;
          const picture = participant.tracks?.video?.persistentTrack;
          if (!audio || !picture || participant.tracks.audio.state !== 'playable' ||
              participant.tracks.video.state !== 'playable') return;
          participantId = participant.session_id;
          video.srcObject = new MediaStream([picture, audio]);
          video.muted = false;
          video.play().then(() => {
            if (settled) return;
            videoBox.classList.add('has-live-avatar');
            call.sendAppMessage({
              message_type: 'conversation',
              event_type: 'conversation.echo',
              conversation_id: room.conversation_id,
              properties: { modality: 'text', text: question.question, inference_id: inferenceId, done: true },
            }, participantId);
          }).catch(finish);
        }

        connection.signal.addEventListener('abort', aborted, { once: true });
        call.on('app-message', onMessage);
        call.on('participant-joined', onParticipant);
        call.on('participant-updated', onParticipant);
        call.join({ url: room.conversation_url, token: room.meeting_token })
          .then(() => Object.values(call.participants()).forEach(participant => onParticipant({ participant })))
          .catch(finish);
      });
    })().catch(error => {
      close();
      throw error;
    });

    return { finished, close };
  }

  window.PlaceAIModuleHRAvatar = { play };
})();
