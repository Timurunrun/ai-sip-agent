Streaming Audio

Getting Started

An introduction to getting transcription data from live streaming audio in real time.
Streaming

In this guide, you’ll learn how to automatically transcribe live streaming audio in real time using Deepgram’s SDKs, which are supported for use with the Deepgram API. (If you prefer not to use a Deepgram SDK, jump to the section Non-SDK Code Examples.)

Before you start, you’ll need to follow the steps in the Make Your First API Request guide to obtain a Deepgram API key, and configure your environment if you are choosing to use a Deepgram SDK.
SDKs

To transcribe audio from an audio stream using one of Deepgram’s SDKs, follow these steps.
Install the SDK

Open your terminal, navigate to the location on your drive where you want to create your project, and install the Deepgram SDK.

# Install the Deepgram Python SDK

# https://github.com/deepgram/deepgram-python-sdk

pip install deepgram-sdk

Add Dependencies

# Install python-dotenv to protect your API key

pip install python-dotenv

Transcribe Audio from a Remote Stream

The following code shows how to transcribe audio from a remote audio stream. If you would like to learn how to stream audio from a microphone, check out our Live Audio Starter Apps or specific examples in the readme of each of the Deepgram SDKs.

# Example filename: main.py

import httpx

import logging

from deepgram.utils import verboselogs

import threading

from deepgram import (

    DeepgramClient,

    DeepgramClientOptions,

    LiveTranscriptionEvents,

    LiveOptions,

)

# URL for the realtime streaming audio you would like to transcribe

URL = "http://stream.live.vc.bbcmedia.co.uk/bbc_world_service"

def main():

    try:

        # use default config

        deepgram: DeepgramClient = DeepgramClient()

        # Create a websocket connection to Deepgram

        dg_connection = deepgram.listen.websocket.v("1")

        def on_message(self, result, **kwargs):

            sentence = result.channel.alternatives[0].transcript

            if len(sentence) == 0:

                return

            print(f"speaker: {sentence}")

        dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)

        # connect to websocket

        options = LiveOptions(model="nova-3")

        print("\n\nPress Enter to stop recording...\n\n")

        if dg_connection.start(options) is False:

            print("Failed to start connection")

            return

        lock_exit = threading.Lock()

        exit = False

        # define a worker thread

        def myThread():

            with httpx.stream("GET", URL) as r:

                for data in r.iter_bytes():

                    lock_exit.acquire()

                    if exit:

                        break

                    lock_exit.release()

                    dg_connection.send(data)

        # start the worker thread

        myHttp = threading.Thread(target=myThread)

        myHttp.start()

        # signal finished

        input("")

        lock_exit.acquire()

        exit = True

        lock_exit.release()

        # Wait for the HTTP thread to close and join

        myHttp.join()

        # Indicate that we've finished

        dg_connection.finish()

        print("Finished")

    except Exception as e:

        print(f"Could not open socket: {e}")

        return

if __name__ == "__main__":

    main()

The above example includes the parameter model=nova-3, which tells the API to use Deepgram’s latest model. Removing this parameter will result in the API using the default model, which is currently model=base.

It also includes Deepgram’s Smart Formatting feature, smart_format=true. This will format currency amounts, phone numbers, email addresses, and more for enhanced transcript readability.
Non-SDK Code Examples

If you would like to try out making a Deepgram speech-to-text request in a specific language (but not using Deepgram’s SDKs), we offer a library of code-samples in this Github repo

. However, we recommend first trying out our SDKs.
Results

In order to see the results from Deepgram, you must run the application. Run your application from the terminal. Your transcripts will appear in your shell.

# Run your application using the file you created in the previous step

# Example: python main.py

python YOUR_PROJECT_NAME.py

Deepgram does not store transcripts, so the Deepgram API response is the only opportunity to retrieve the transcript. Make sure to save output or return transcriptions to a callback URL for custom processing.
Analyze the Response

The responses that are returned will look similar to this:
JSON

{

  "type": "Results",

  "channel_index": [

    0,

    1

  ],

  "duration": 1.98,

  "start": 5.99,

  "is_final": true,

  "speech_final": true,

  "channel": {

    "alternatives": [

      {

        "transcript": "Tell me more about this.",

        "confidence": 0.99964225,

        "words": [

          {

            "word": "tell",

            "start": 6.0699997,

            "end": 6.3499994,

            "confidence": 0.99782443,

            "punctuated_word": "Tell"

          },

          {

            "word": "me",

            "start": 6.3499994,

            "end": 6.6299996,

            "confidence": 0.9998324,

            "punctuated_word": "me"

          },

          {

            "word": "more",

            "start": 6.6299996,

            "end": 6.79,

            "confidence": 0.9995466,

            "punctuated_word": "more"

          },

          {

            "word": "about",

            "start": 6.79,

            "end": 7.0299997,

            "confidence": 0.99984455,

            "punctuated_word": "about"

          },

          {

            "word": "this",

            "start": 7.0299997,

            "end": 7.2699995,

            "confidence": 0.99964225,

            "punctuated_word": "this"

          }

        ]

      }

    ]

  },

  "metadata": {

    "request_id": "52cc0efe-fa77-4aa7-b79c-0dda09de2f14",

    "model_info": {

      "name": "2-general-nova",

      "version": "2024-01-18.26916",

      "arch": "nova-2"

    },

    "model_uuid": "c0d1a568-ce81-4fea-97e7-bd45cb1fdf3c"

  },

  "from_finalize": false

}

In this default response, we see:

    transcript: the transcript for the audio segment being processed.

    confidence: a floating point value between 0 and 1 that indicates overall transcript reliability. Larger values indicate higher confidence.

    words: an object containing each word in the transcript, along with its start time and end time (in seconds) from the beginning of the audio stream, and a confidence value.
        Because we passed the smart_format: true option to the transcription.prerecorded method, each word object also includes its punctuated_word value, which contains the transformed word after punctuation and capitalization are applied.

    speech_final: tells us this segment of speech naturally ended at this point. By default, Deepgram live streaming looks for any deviation in the natural flow of speech and returns a finalized response at these places. To learn more about this feature, see Endpointing.

    is_final: If this says false, it is indicating that Deepgram will continue waiting to see if more data will improve its predictions. Deepgram live streaming can return a series of interim transcripts followed by a final transcript. To learn more, see Interim Results.

Endpointing can be used with Deepgram’s Interim Results feature. To compare and contrast these features, and to explore best practices for using them together, see Using Endpointing and Interim Results with Live Streaming Audio.

If your scenario requires you to keep the connection alive even while data is not being sent to Deepgram, you can send periodic KeepAlive messages to essentially “pause” the connection without closing it. To learn more, see KeepAlive.
What’s Next?

Now that you’ve gotten transcripts for streaming audio, enhance your knowledge by exploring the following areas. You can also check out our Live Streaming API Reference for a list of all possible parameters.
Try the Starter Apps

    Clone and run one of our Live Audio Starter App repositories to see a full application with a frontend UI and a backend server streaming audio to Deepgram.

Read the Feature Guides

Deepgram’s features help you to customize your transcripts.

    Language: Learn how to transcribe audio in other languages.
    Feature Overview: Review the list of features available for streaming speech-to-text. Then, dive into individual guides for more details.

Tips and tricks

    End of speech detection - Learn how to pinpoint end of speech post-speaking more effectively.
    Using interim results - Learn how to use preliminary results provided during the streaming process which can help with speech detection.
    Measuring streaming latency - Learn how to measure latency in real-time streaming of audio.

Add Your Audio

    Ready to connect Deepgram to your own audio source? Start by reviewing how to determine your audio format and format your API request accordingly.
    Then, check out our Live Streaming Starter Kit. It’s the perfect “102” introduction to integrating your own audio.

Explore Use Cases

    Learn about the different ways you can use Deepgram products to help you meet your business objectives. Explore Deepgram’s use cases.

Transcribe Pre-recorded Audio

    Now that you know how to transcribe streaming audio, check out how you can use Deepgram to transcribe pre-recorded audio. To learn more, see Getting Started with Pre-recorded Audio.

Streaming Audio
Control Messages

Close Stream

Learn how to send Deepgram a CloseStream message, which closes the websocket stream.
Streaming

In real-time audio processing, there are scenarios where you may need to force the server to close. Deepgram supports a CloseStream message to handle such situations. This message will send a shutdown command to the server instructing it to finish processing any cached data, send the response to the client, send a summary metadata object, and then terminate the WebSocket connection.
What is the CloseStream Message

The CloseStream message is a JSON command that you send to the Deepgram server, instructing it close the connection. This is particularly useful in scenarios where you need to immediately shutdown the websocket connection and process and return all data to the client.
Sending CloseStream

To send the CloseStream message, you need to send the following JSON message to the server:
JSON

{ 

  "type": "CloseStream" 

}

CloseStream Confirmation

Upon receiving the CloseStream message, the server will process all remaining audio data and return the following:
JSON

{

    "type": "Metadata",

    "transaction_key": "deprecated",

    "request_id": "8c8ebea9-dbec-45fa-a035-e4632cb05b5f",

    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",

    "created": "2024-08-29T22:37:55.202Z",

    "duration": 0.0,

    "channels": 0

}

Language-Specific Implementations

import json

import websocket

# Assuming 'headers' is already defined for authorization

ws = websocket.create_connection("wss://api.deepgram.com/v1/listen", header=headers)

# Construct CloseStream message

closestream_msg = json.dumps({"type": "CloseStream"})

# Send CloseStream message

ws.send(closestream_msg)

Conclusion

In summary, when dealing with real-time audio processing, there are situations where it may be necessary to forcibly close the server connection. Deepgram provides the CloseStream message to facilitate this process. By sending this message, the server is instructed to complete processing any buffered data, return the final response along with summary metadata, and then gracefully terminate the WebSocket connection. This ensures a controlled shutdown, preserving the integrity of the data and the overall process.

Streaming Audio
Control Messages

Finalize

Learn how to send Deepgram a Finalize message, which flushes the websocket stream’s audio by forcing the server to process all unprocessed audio data immediately and return the results.
Streaming

In real-time audio processing, there are scenarios where you may need to force the server to process (or flush) all unprocessed audio data immediately. Deepgram supports a Finalize message to handle such situations, ensuring that interim results are treated as final.
What is the Finalize Message?

The Finalize message is a JSON command that you send to the Deepgram server, instructing it to process and finalize all remaining audio data immediately. This is particularly useful in scenarios where an utterance has ended, or when transitioning to a keep-alive period to ensure that no previous transcripts reappear unexpectedly.
Sending Finalize

To send the Finalize message, you need to send the following JSON message to the server:
JSON

{

  "type": "Finalize"

}

You can optionally specify a channel field to finalize a specific channel. If the channel field is omitted, all channels in the audio will be finalized. Note that channel indexing starts at 0, so to finalize only the first channel you need to send:
JSON

{

  "type": "Finalize",

   "channel": 0

}

Finalize Confirmation

Upon receiving the Finalize message, the server will process all remaining audio data and return the final results. You may receive a response with the from_finalize attribute set to true, indicating that the finalization process is complete. This response typically occurs when there is a noticeable amount of audio buffered in the server.

If you specified a channel to be finalized, use the response’s channel_index field to check which channel was finalized.
JSON

{

  "from_finalize": true

}

In most cases, you will receive this response, but it is not guaranteed if there is no significant amount of audio data to process.
Language-Specific Implementations

Following are code examples to help you get started.
Sending a Finalize message in JSON Format

These snippets demonstrate how to construct a JSON message containing the “Finalize” type and send it over the WebSocket connection in each respective language.

import json

import websocket

# Assuming 'headers' is already defined for authorization

ws = websocket.create_connection("wss://api.deepgram.com/v1/listen", header=headers)

# Construct Finalize message

finalize_msg = json.dumps({"type": "Finalize"})

# Send Finalize message

ws.send(finalize_msg)

Streaming Examples

Here are more complete examples that make a streaming request and use Finalize. Try running these examples to see how Finalize can be sent to Deepgram, forcing the API to process all unprocessed audio data and immediately return the results.

from websocket import WebSocketApp

import websocket

import json

import threading

import requests

import time

auth_token = "YOUR_DEEPGRAM_API_KEY"  # Replace with your actual authorization token

headers = {

    "Authorization": f"Token {auth_token}"

}

# WebSocket URL

ws_url = "wss://api.deepgram.com/v1/listen"

# Audio stream URL

audio_url = "http://stream.live.vc.bbcmedia.co.uk/bbc_world_service"

# Define the WebSocket functions on_open, on_message, on_close, and on_error

def on_open(ws):

    print("WebSocket connection established.")

    

    # Start audio streaming thread

    audio_thread = threading.Thread(target=stream_audio, args=(ws,))

    audio_thread.daemon = True

    audio_thread.start()

    

    # Finalize test thread

    finalize_thread = threading.Thread(target=finalize_test, args=(ws,))

    finalize_thread.daemon = True

    finalize_thread.start()

def on_message(ws, message):

    try:

        response = json.loads(message)

        if response.get("type") == "Results":

            transcript = response["channel"]["alternatives"][0].get("transcript", "")

            if transcript:

                print("Transcript:", transcript)

        

            # Check if this is the final result from finalize

            # Note: in most cases, you will receive this response, but it is not guaranteed if there is no significant amount of audio data left to process.

            if response.get("from_finalize", False):

                print("Finalization complete.")

    except json.JSONDecodeError as e:

        print(f"Error decoding JSON message: {e}")

    except KeyError as e:

        print(f"Key error: {e}")

def on_close(ws, close_status_code, close_msg):

    print(f"WebSocket connection closed with code: {close_status_code}, message: {close_msg}")

def on_error(ws, error):

    print("WebSocket error:", error)

# Define the function to stream audio to the WebSocket

def stream_audio(ws):

    response = requests.get(audio_url, stream=True)

    if response.status_code == 200:

        print("Audio stream opened.")

        for chunk in response.iter_content(chunk_size=4096):

            ws.send(chunk, opcode=websocket.ABNF.OPCODE_BINARY)

    else:

        print("Failed to open audio stream:", response.status_code)

# Define the function to send the Finalize message

def finalize_test(ws):

    # Wait for 10 seconds before sending the Finalize message to simulate the end of audio streaming

    time.sleep(10)

    finalize_message = json.dumps({"type": "Finalize"})

    ws.send(finalize_message)

    print("Finalize message sent.")

# Create WebSocket connection

ws = WebSocketApp(ws_url, on_open=on_open, on_message=on_message, on_close=on_close, on_error=on_error, header=headers)

# Run the WebSocket

ws.run_forever()

Conclusion

Using the Finalize message with Deepgram’s API allows for precise control over the finalization of audio processing. This feature is essential for scenarios requiring immediate processing of the remaining audio data, ensuring accurate and timely results.

Streaming Audio
Control Messages

Audio Keep Alive

Learn how to send messages while streaming audio, ensuring uninterrupted communication.
Streaming

KeepAlive serves as a crucial mechanism for maintaining an uninterrupted connection with Deepgram’s servers, allowing you to optimize your audio streaming experience while minimizing costs.
What is theKeepAlive message?

A common situation is needing to keep a connection open without constantly sending audio. Normally, you’d have to send data all the time, even silence, which wastes resources and increases costs since Deepgram charges for all audio, whether it’s speech or silence. KeepAlive solves this by allowing you to pause the connection and resume later, avoiding extra costs for transcribing silence.
Benefits

    Cost Efficiency: KeepAlive enables you to optimize costs by pausing the connection during periods of silence, eliminating the need to transcribe unnecessary audio data.
    Connection Maintenance: By sending periodic KeepAlive messages, you can ensure that the WebSocket connection remains open, preventing timeouts and maintaining communication with Deepgram’s servers.
    Flexibility: KeepAlive offers flexibility in managing your streaming sessions. You can temporarily halt the transmission of audio data while keeping the connection active, resuming data streaming when needed without re-establishing the connection.

Sending KeepAlive

To send the KeepAlive message, you need to send the following JSON message to the server:
JSON

{

  "type": "KeepAlive" 

}

Because Deepgram’s streaming connection is set to time out after 10 seconds of inactivity, it’s essential to periodically send KeepAlive messages to maintain the connection and prevent it from closing prematurely.

If no audio data is sent within a 10-second window, the connection will close, triggering a NET-0001 error. Using KeepAlive extends the connection by another 10 seconds. To avoid this error and keep the connection open, continue sending KeepAlive messages 3-5 seconds before the 10 second timeout window expires until you are ready to resume sending audio.

Be sure to send the KeepAlive message as a text WebSocket message. Sending it as a binary message may result in incorrect handling and could lead to connection issues.
KeepAlive Confirmation

You will not receive a response back from the server.
Language Specific Implementations

Following are code examples to help you get started.
Sending a KeepAlive message in JSON Format

These snippets demonstrate how to construct a JSON message containing the KeepAlive type and send it over the WebSocket connection in each respective language.

import json

import websocket

# Assuming 'headers' is already defined for authorization

ws = websocket.create_connection("wss://api.deepgram.com/v1/listen", header=headers)

# Assuming 'ws' is the WebSocket connection object

keep_alive_msg = json.dumps({"type": "KeepAlive"})

ws.send(keep_alive_msg)

Streaming Examples

Here are more complete examples that make a streaming request and use KeepAlive. Try running these examples to see how KeepAlive is sent periodically.

import websocket

import json

import time

import threading

auth_token = "DEEPGRAM_API_KEY"  # Replace 'DEEPGRAM_API_KEY' with your actual authorization token

headers = {

    "Authorization": f"Token {auth_token}"

}

# WebSocket URL

ws_url = "wss://api.deepgram.com/v1/listen"

# Define the WebSocket on_open function

def on_open(ws):

    print("WebSocket connection established.")

    # Send KeepAlive messages every 3 seconds

    def keep_alive():

        while True:

            keep_alive_msg = json.dumps({"type": "KeepAlive"})

            ws.send(keep_alive_msg)

            print("Sent KeepAlive message")

            time.sleep(3)

    # Start a thread for sending KeepAlive messages

    keep_alive_thread = threading.Thread(target=keep_alive)

    keep_alive_thread.daemon = True

    keep_alive_thread.start()

# Define the WebSocket on_message function

def on_message(ws, message):

    print("Received:", message)

    # Handle received data (transcription results, errors, etc.)

# Define the WebSocket on_close function

def on_close(ws):

    print("WebSocket connection closed.")

# Define the WebSocket on_error function

def on_error(ws, error):

    print("WebSocket error:", error)

# Create WebSocket connection

ws = websocket.WebSocketApp(ws_url,

                            on_open=on_open,

                            on_message=on_message,

                            on_close=on_close,

                            on_error=on_error,

                            header=headers)

# Run the WebSocket

ws.run_forever()

Deepgram SDKs

Deepgram’s SDKs make it easier to build with Deepgram in your preferred language. To learn more about getting started with the SDKs, visit Deepgram’s SDKs documentation.

from deepgram import DeepgramClient, DeepgramClientOptions, LiveTranscriptionEvents, LiveOptions

API_KEY = "DEEPGRAM_API_KEY"

def main():

    try:

        config = DeepgramClientOptions(

            options={"keepalive": "true"} # Comment this out to see the effect of not using keepalive

        )

        

        deepgram = DeepgramClient(API_KEY, config)

        dg_connection = deepgram.listen.live.v("1")

        def on_message(self, result, **kwargs):

            sentence = result.channel.alternatives[0].transcript

            if len(sentence) == 0:

                return

            print(f"speaker: {sentence}")

        def on_metadata(self, result, **kwargs):

            print(f"\n\n{result}\n\n")

        def on_error(self, error, **kwargs):

            print(f"\n\n{error}\n\n")

        dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)

        dg_connection.on(LiveTranscriptionEvents.Metadata, on_metadata)

        dg_connection.on(LiveTranscriptionEvents.Error, on_error)

        options = LiveOptions(

            model="nova-3", 

            language="en-US", 

            smart_format=True,

        )

        

        dg_connection.start(options)

    except Exception as e:

        print(f"Could not open socket: {e}")

if __name__ == "__main__":

    main()

Word Timings

Word timings for transcription results returned from a stream are based on the audio sent, not the lifetime of the websocket. If you send KeepAlive messages without sending audio payloads for a period of time, then resume sending audio payloads, the timestamps for transcription results will pick up where they left off when you paused sending audio payloads.

Here is an example timeline demonstrating the behavior:
Event	Wall Time	Word Timing Range on Results Response
Websocket opened, begin sending audio payloads	0 seconds	0 seconds
Results received	5 seconds	0-5 seconds
Results received	10 seconds	5-10 seconds
Pause sending audio payloads, while sending KeepAlive messages	10 seconds	n/a
Resume sending audio payloads	30 seconds	n/a
Results received	35 seconds	10-15 seconds

Streaming Audio
Speech Detection

Speech Started

Speech Started sends a message when the start of speech is detected in live streaming audio.

vad_events boolean.
Pre-recorded
Streaming
All available languages

Deepgram’s Speech Started feature can be used for speech detection and can be used to detect the start of speech while transcribing live streaming audio.

SpeechStarted complements Voice Activity Detection (VAD) to promptly detect the start of speech post-silence. By gauging tonal nuances in human speech, the VAD can effectively differentiate between silent and non-silent audio segments, providing immediate notification of speech detection.
Enable Feature

To enable the SpeechStarted event, include the parameter vad_events=true in your request:

vad_events=true

You’ll then begin receiving messages upon speech starting.
Python

# see https://github.com/deepgram/deepgram-python-sdk/blob/main/examples/streaming/async_microphone/main.py

# for complete example code

   options: LiveOptions = LiveOptions(

            model="nova-3",

            language="en-US",

            # Apply smart formatting to the output

            smart_format=True,

            # Raw audio format details

            encoding="linear16",

            channels=1,

            sample_rate=16000,

            # To get UtteranceEnd, the following must be set:

            interim_results=True,

            utterance_end_ms="1000",

            vad_events=True,

            # Time in milliseconds of silence to wait for before finalizing speech

            endpointing=300

        )

Results

The JSON message sent when the start of speech is detected looks similar to this:
JSON

{

  "type": "SpeechStarted",

  "channel": [

    0,

    1

  ],

  "timestamp": 9.54

}

    The type field is always SpeechStarted for this event.
    The channel field is interpreted as [A,B], where A is the channel index, and B is the total number of channels. The above example is channel 0 of single-channel audio.
    The timestamp field is the time at which speech was first detected.

The timestamp doesn’t always match the start time of the first word in the next transcript because the systems for transcribing and timing words work independently of the speech detection system.

Streaming Audio
Speech Detection

Utterance End

Utterance End sends a message when the end of speech is detected in live streaming audio.

utterance_end_ms string.
Pre-recorded
Streaming
All available languages

The UtteranceEnd feature can be used for speech detection and can be enabled to help detect the end of speech while transcribing live streaming audio.

UtteranceEnd complements Voice Activity Detection (VAD) by analyzing word timings in both interim and finalized transcripts to detect gaps between words, marking the end of spoken utterances and notifying users of speech endpoint detection.
Enable Feature

To enable this feature, add utterance_end_ms=000 to your request. Replace 000 with the number of milliseconds you want Deepgram to wait before sending the UtteranceEnd message.

For example, if you set utterance_end_ms=1000, Deepgram will wait for a 1000 millisecond gap between transcribed words before sending the UtteranceEnd message.

It is recommended that you set the value of utterance_end_ms to be 1000 ms or higher.

UtteranceEnd relies on Deepgram’s interim_results feature and Deepgram’s Interim Results are typically sent every second, so using a value of less 1000ms for utterance_end_ms will not offer you any benefits.

When using utterance_end_ms, setting interim_results=true is also required.
Python

# see https://github.com/deepgram/deepgram-python-sdk/blob/main/examples/streaming/async_microphone/main.py

# for complete example code

   options: LiveOptions = LiveOptions(

            model="nova-3",

            language="en-US",

            # Apply smart formatting to the output

            smart_format=True,

            # Raw audio format details

            encoding="linear16",

            channels=1,

            sample_rate=16000,

            # To get UtteranceEnd, the following must be set:

            interim_results=True,

            utterance_end_ms="1000",

            vad_events=True,

            # Time in milliseconds of silence to wait for before finalizing speech

            endpointing=300

        )

Results

The UtteranceEnd JSON message will look similar to this:
JSON

{

  "channel": [

    0,

    1

  ],

  "last_word_end": 2.395,

  "type": "UtteranceEnd"

}

    The type field is always UtteranceEnd for this event.
    The channel field is interpreted as [A,B], where A is the channel index, and B is the total number of channels. The above example is channel 0 of single-channel audio.
    The last_word_end field is the time at which end of speech was detected.

If you compare this to the Results response below, you will see that the last_word_end from the UtteranceEnd response matches the data in the alternatives[0].words[1].end field of the Results response. This is due to the gap identified after the final word.

In addition, you can see is_final=true, which is sent because of the interim_results feature.
JSON

{

  "channel": {

    "alternatives": [

      {

        "confidence": 0.77905273,

        "transcript": "Testing. 123.",

        "words": [

          {

            "confidence": 0.69189453,

            "end": 1.57,

            "punctuated_word": "Testing.",

            "start": 1.07,

            "word": "testing"

          },

          {

            "confidence": 0.77905273,

            "end": 2.395,

            "punctuated_word": "123.",

            "start": 1.895,

            "word": "123"

          }

        ]

      }

    ]

  },

  "channel_index": [

    0,

    1

  ],

  "duration": 1.65,

  "is_final": true,

  "metadata": {

   ...

  "type": "Results"

}

Streaming Audio
Speech Detection

Endpointing

Endpointing returns transcripts when pauses in speech are detected.

endpointing string.
Pre-recorded
Streaming
All available languages

Deepgram’s Endpointing feature can be used for speech detection by monitoring incoming streaming audio and relies on a Voice Activity Detector (VAD), which monitors the incoming audio and triggers when a sufficiently long pause is detected.

Endpointing helps to detects sufficiently long pauses that are likely to represent an endpoint in speech. When an endpoint is detected the model assumes that no additional data will improve it’s prediction of the endpoint.

The transcript results are then finalized for the process time range and the JSON response is returned with a speech_final parameter set to true.

You can customize the length of time used to detect whether a speaker has finished speaking by setting the endpointing parameter to an integer value.

Endpointing can be used with Deepgram’s Interim Results feature. To compare and contrast these features, and to explore best practices for using them together, see Using Endpointing and Interim Results with Live Streaming Audio.
Enable Feature

Endpointing is enabled by default and set to 10 milliseconds. and will return transcripts after detecting 10 milliseconds of silence.

The period of silence required for endpointing may also be configured. When you call Deepgram’s API, add an endpointing parameter set to an integer by setting endpointing to an integer representing a millisecond value:

endpointing=500

This will wait until 500 milliseconds of silence has passed to finalize and return transcripts.

Endpointing may be disabled by setting endpointing=false. If endpointing is disabled, transcriptions will be returned at a cadence determined by Deepgram’s chunking algorithms.
Python

# see https://github.com/deepgram/deepgram-python-sdk/blob/main/examples/streaming/async_microphone/main.py

# for complete example code

   options: LiveOptions = LiveOptions(

            model="nova-3",

            language="en-US",

            # Apply smart formatting to the output

            smart_format=True,

            # Raw audio format details

            encoding="linear16",

            channels=1,

            sample_rate=16000,

            # To get UtteranceEnd, the following must be set:

            interim_results=True,

            utterance_end_ms="1000",

            vad_events=True,

            # Time in milliseconds of silence to wait for before finalizing speech

            endpointing=300

        )

Results

When enabled, the transcript for each received streaming response shows a key called speech_final.
JSON

{

  "channel_index":[

    0,

    1

  ],

  "duration":1.039875,

  "start":0.0,

  "is_final":false,

  "speech_final":true,

  "channel":{

    "alternatives":[

      {

        "transcript":"another big",

        "confidence":0.9600255,

        "words":[

          {

            "word":"another",

            "start":0.2971154,

            "end":0.7971154,

            "confidence":0.9588303

          },

          {

            "word":"big",

            "start":0.85173076,

            "end":1.039875,

            "confidence":0.9600255

          }

        ]

      }

    ]

  }

}

...

Streaming Audio
Tips and Tricks

End of Speech Detection While Live Streaming

Learn how to use End of Speech when transcribing live streaming audio with Deepgram.

To pinpoint the end of speech post-speaking more effectively, immediate notification of speech detection is preferred over relying on the initial transcribed word inference. This is achieved through a Voice Activity Detector (VAD), which gauges the tonal nuances of human speech and can better differentiate between silent and non-silent audio.
Limitations of Endpointing

Deepgram’s Endpointing and Interim Results features are designed to detect when a speaker finishes speaking.

Deepgram’s Endpointing feature uses an audio-based Voice Activity Detector (VAD) to determine when a person is speaking and when there is silence. When the state of the audio goes from speech to a configurable duration of silence (set by the endpointing query parameter), Deepgram will chunk the audio and return a transcript with the speech_final flag set to true.

For more information, see Understanding Endpointing and Interim Results When Transcribing Live Streaming Audio).

In a quiet room with little background noise, Deepgram’s Endpointing feature works well. In environments with significant background noise such as playing music, a ringing phone, or at a fast food drive thru, the background noise can cause the VAD to trigger and prevent the detection of silent audio. Since endpointing only fires after a certain amount of silence has been detected, a significant amount of background noise may prevent the speech_final=true flag from being sent.

In rare situations, such as when speaking a phone number, Deepgram may purposefully wait for additional audio from the speaker so it can properly format the transcript (this only occurs when using smart_format=true).
Using UtteranceEnd

To address the limitations described above, Deepgram offers the UtteranceEnd feature. The UtteranceEnd feature looks at the word timings of both finalized and interim results to determine if a sufficiently long gap in words has occurred. If it has, Deepgram will send a JSON message over the websocket with following shape:
JSON

{"type":"UtteranceEnd", "channel": [0,2], "last_word_end": 3.1}

Your app can wait for this message to be sent over the websocket to identify when the speaker has stopped talking, even if significant background noise is present.

The "channel" field is interpreted as [A,B], where A is the channel index, and B is the total number of channels. The above example is channel 0 of two-channel audio.

The "last_word_end" field is the end timestamp of the last word spoken before the utterance ended on the channel. This timestamp can be used to match against the earlier word-level transcript to identify which word was last spoken before the utterance end message was triggered.

To enable this feature, add the query parameter utterance_end_ms=1234 to your websocket URL and replace 1234 with the number of milliseconds you want Deepgram to wait before sending the UtteranceEnd message.

For example, if you set utterance_end_ms=1000 Deepgram will wait for a 1000 ms gaps between transcribed words before sending the UtteranceEnd message. Since this feature relies on word timings in the message transcript, it ignores non-speech audio such as: door knocking, a phone ringing or street noise.

You should set the value of utterance_end_ms to be 1000 ms or higher. Deepgram’s Interim Results are sent every 1 second, so using a value of less than 1 second will not offer any benefits.

When using utterance_end_ms, setting interim_results=true is also required.
Using UtteranceEnd and Endpointing

You can use both the Endpointing and UtteranceEnd features. They operate completely independently from one another, so it is possible to use both at the same time. When using both features in your app, you may want to trigger your “speaker has finished speaking” logic using the following rules:

    trigger when a transcript with speech_final=true is received (which may be followed by an UtteranceEnd message which can be ignored),
    trigger if you receive an UtteranceEnd message with no preceding speech_final=true message and send the last-received transcript for further processing.

Additional Consideration

Ultimately, any approach to determine when someone has finished speaking is a heuristic one and may fail in rare situations. Since humans can resume talking at any time for any reason, detecting when a speaker has finished speaking or completed their thought is very difficult. To mitigate these concerns for your product, you may need to determine what constitutes “end of thought” or “end of speech” for your customers. For example, a voice-journaling app may need to allow for long pauses before processing the text, but a food ordering app may need to process the audio every few words.

Streaming Audio
Tips and Tricks

Determining Your Audio Format for Live Streaming Audio

Learn how to determine if your audio is containerized or raw, and what this means for correctly formatting your requests to Deepgram’s API.

Before you start streaming audio to Deepgram, it’s important that you understand whether your audio is containerized or raw, so you can correctly form your API request.

The difference between containerized and raw audio relates to how much information about the audio is included within the data:

    Containerized audio stream: A series of bits is passed along with a header that specifies information about the audio. Containerized audio generally includes enough additional information to allow Deepgram to decode it automatically.
    Raw audio stream: The series of bits is passed with no further information. Deepgram needs you to manually provide information about the characteristics of raw audio.

Streaming Raw Audio

If you’re streaming raw audio to Deepgram, you must provide the encoding and sample rate of your audio stream in your request. Otherwise, Deepgram will be unable to decode the audio and will fail to return a transcript.

An example of a Deepgram API request to stream raw audio:

wss://api.deepgram.com/v1/listen?encoding=ENCODING_VALUE&sample_rate=SAMPLE_RATE_VALUE

To see a list of raw audio encodings that Deepgram supports, check out our Encoding documentation.
Streaming Containerized Audio

If you’re streaming containerized audio to Deepgram, you should not set the encoding and sample rate of your audio stream. Instead, Deepgram will read the container’s header and get the correct information for your stream automatically.

An example of a Deepgram API request to stream containerized audio:

wss://api.deepgram.com/v1/listen

Deepgram supports over 100 different audio formats and encodings. You can see some of the most popular ones at Supported Audio Format.
Determining Your Audio Format

If you’re not sure whether your audio is raw or containerized, you can identify audio format in a few different ways.
Check Documentation

Start by checking any available documentation for your audio source. Often, it will provide details related to audio format. Specifically, check for any mentions of encodings like Opus, Vorbis, PCM, mu-law, A-law, s16, or linear16.

If your audio source is a web API stream, in many cases it will already be containerized. For example, the audio may be raw Opus audio wrapped in an Ogg container or raw PCM audio wrapped in a WAV container.
Automatically Detect Audio Format

If you’re still not sure whether or not your audio is containerized, you can write an audio stream to disk and try listening to it with a program like VLC. If your audio is containerized, VLC will be able to play it back without any additional configuration.

Alternatively, you can use ffprobe (part of the ffmpeg package, which is a cross-platform solution that records, converts, and streams audio and video) to gather information from the audio stream and detect the audio format of a file.

To use ffprobe, from a terminal, run:
Shell

ffprobe PATH_TO_FILE

The last line of the output from this command will include any data ffprobe is able to determine about the file’s audio format.
Using Raw Audio with Encoding & Sample Rate

When using raw audio, make sure to set the encoding and the sample rate. Both parameters are required for Deepgram to be able to decode your stream.


API REF:
API Reference
Speech to Text API
Live Audio

Deepgram Speech to Text WebSocket
Handshake
GET
Headers
AuthorizationstringRequired

API key for authentication. Format should be be either ‘token <DEEPGRAM_API_KEY>’ or ‘Bearer <JWT_TOKEN>’
Query parameters
callbackstringOptional

URL to which we’ll make the callback request
callback_methodenumOptionalDefaults to POST

HTTP method by which the callback request will be made
Allowed values: POSTGETPUTDELETE
channelsstringOptionalDefaults to 1

The number of channels in the submitted audio
diarizebooleanOptional

Defaults to false. Recognize speaker changes. Each word in the transcript will be assigned a speaker number starting at 0
dictationenumOptionalDefaults to false

Identify and extract key entities from content in submitted audio
Allowed values: truefalse
encodingenumOptional

Specify the expected encoding of your submitted audio
linear16flacmulawamr-nbamr-wbopusspeexg729
endpointingstringOptionalDefaults to 10

Indicates how long Deepgram will wait to detect whether a speaker has finished speaking or pauses for a significant period of time. When set to a value, the streaming endpoint immediately finalizes the transcription for the processed time range and returns the transcript with a speech_final parameter set to true. Can also be set to false to disable endpointing
extrastringOptional

Arbitrary key-value pairs that are attached to the API response for usage in downstream processing
filler_wordsenumOptionalDefaults to false

Filler Words can help transcribe interruptions in your audio, like “uh” and “um”
Allowed values: truefalse
interim_resultsenumOptionalDefaults to false

Specifies whether the streaming endpoint should provide ongoing transcription updates as more audio is received. When set to true, the endpoint sends continuous updates, meaning transcription results may evolve over time
Allowed values: truefalse
keytermlist of stringsOptional

Key term prompting can boost or suppress specialized terminology and brands. Only compatible with Nova-3
keywordsstringOptional

Keywords can boost or suppress specialized terminology and brands
languageenumOptionalDefaults to en

The BCP-47 language tag

that hints at the primary spoken language. Depending on the Model you choose only certain languages are available
bgcacsdada-DKdede-CHelenen-AUen-GBen-INen-NZen-USeses-419es-LATAMetfifrfr-CAhihi-Latnhuiditjakoko-KRltlvmsnlnl-BEnoplptpt-BRpt-PTrorusksvsv-SEtaqthth-THtrukvizhzh-CNzh-HKzh-Hanszh-Hantzh-TW
modelenumOptional

AI model to use for the transcription
nova-3nova-3-generalnova-3-medicalnova-2nova-2-generalnova-2-meetingnova-2-financenova-2-conversationalainova-2-voicemailnova-2-videonova-2-medicalnova-2-drivethrunova-2-automotivenovanova-generalnova-phonecallnova-medicalenhaAPI Reference
Speech to Text API
Live Audio

Deepgram Speech to Text WebSocket
Handshake
GET
Headers
AuthorizationstringRequired

API key for authentication. Format should be be either ‘token <DEEPGRAM_API_KEY>’ or ‘Bearer <JWT_TOKEN>’
Query parameters
callbackstringOptional

URL to which we’ll make the callback request
callback_methodenumOptionalDefaults to POST

HTTP method by which the callback request will be made
Allowed values: POSTGETPUTDELETE
channelsstringOptionalDefaults to 1

The number of channels in the submitted audio
diarizebooleanOptional

Defaults to false. Recognize speaker changes. Each word in the transcript will be assigned a speaker number starting at 0
dictationenumOptionalDefaults to false

Identify and extract key entities from content in submitted audio
Allowed values: truefalse
encodingenumOptional

Specify the expected encoding of your submitted audio
linear16flacmulawamr-nbamr-wbopusspeexg729
endpointingstringOptionalDefaults to 10

Indicates how long Deepgram will wait to detect whether a speaker has finished speaking or pauses for a significant period of time. When set to a value, the streaming endpoint immediately finalizes the transcription for the processed time range and returns the transcript with a speech_final parameter set to true. Can also be set to false to disable endpointing
extrastringOptional

Arbitrary key-value pairs that are attached to the API response for usage in downstream processing
filler_wordsenumOptionalDefaults to false

Filler Words can help transcribe interruptions in your audio, like “uh” and “um”
Allowed values: truefalse
interim_resultsenumOptionalDefaults to false

Specifies whether the streaming endpoint should provide ongoing transcription updates as more audio is received. When set to true, the endpoint sends continuous updates, meaning transcription results may evolve over time
Allowed values: truefalse
keytermlist of stringsOptional

Key term prompting can boost or suppress specialized terminology and brands. Only compatible with Nova-3
keywordsstringOptional

Keywords can boost or suppress specialized terminology and brands
languageenumOptionalDefaults to en

The BCP-47 language tag

that hints at the primary spoken language. Depending on the Model you choose only certain languages are available
bgcacsdada-DKdede-CHelenen-AUen-GBen-INen-NZen-USeses-419es-LATAMetfifrfr-CAhihi-Latnhuiditjakoko-KRltlvmsnlnl-BEnoplptpt-BRpt-PTrorusksvsv-SEtaqthth-THtrukvizhzh-CNzh-HKzh-Hanszh-Hantzh-TW
modelenumOptional

AI model to use for the transcription
nova-3nova-3-generalnova-3-medicalnova-2nova-2-generalnova-2-meetingnova-2-financenova-2-conversationalainova-2-voicemailnova-2-videonova-2-medicalnova-2-drivethrunova-2-automotivenovanova-generalnova-phonecallnova-medicalenhancedenhanced-generalenhanced-meetingenhanced-phonecallenhanced-financebasemeetingphonecallfinanceconversationalaivoicemailvideocustom
multichannelenumOptionalDefaults to false

Transcribe each audio channel independently
Allowed values: truefalse
numeralsenumOptionalDefaults to false

Convert numbers from written format to numerical format
Allowed values: truefalse
profanity_filterenumOptionalDefaults to false

Profanity Filter looks for recognized profanity and converts it to the nearest recognized non-profane word or removes it from the transcript completely
Allowed values: truefalse
punctuateenumOptionalDefaults to false

Add punctuation and capitalization to the transcript
Allowed values: truefalse
redactenumOptionalDefaults to false

Redaction removes sensitive information from your transcripts
truefalsepcinumbersaggressive_numbersssn
replacestringOptional

Search for terms or phrases in submitted audio and replaces them
sample_ratestringOptional

Sample rate of submitted audio. Required (and only read) when a value is provided for encoding
searchstringOptional

Search for terms or phrases in submitted audio
smart_formatenumOptionalDefaults to false

Apply formatting to transcript output. When set to true, additional formatting will be applied to transcripts to improve readability
Allowed values: truefalse
tagstringOptional

Label your requests for the purpose of identification during usage reporting
utterance_endstringOptional

Indicates how long Deepgram will wait to send an UtteranceEnd message after a word has been transcribed. Use with interim_results
vad_eventsenumOptionalDefaults to false

Indicates that speech has started. You’ll begin receiving Speech Started messages upon speech starting
Allowed values: truefalse
versionstringOptionalDefaults to latest

Version of an AI model to use
Send
abc
transcriptionRequeststring
OR
listen_controlMessagesRequestobject
Finalize
type"Finalize"Required
OR
Close Stream
type"CloseStream"Required
OR
Keep Alive
type"KeepAlive"Required
Receive
transcriptionResponseobject
channelobjectOptional
alternativeslist of objectsOptional
metadataobjectOptional
model_infoobjectOptional
request_idstringOptional
format: "uuid"
model_uuidstringOptional
format: "uuid"
typestringOptional
channel_indexlist of integersOptional
durationdoubleOptional
startdoubleOptional
is_finalbooleanOptional
from_finalizebooleanOptional
speech_finalbooleanOptional
OR
Control Message Response Zeroobject
type"Finalize"OptionalDefaults to Finalize
channelintegerOptional
>=0

The channel number being finalized
OR
Control Message Response Oneobject
type"Metadata"OptionalDefaults to Metadata
transaction_keystrinAPI Reference
Speech to Text API
Live Audio

Deepgram Speech to Text WebSocket
Handshake
GET
Headers
AuthorizationstringRequired

API key for authentication. Format should be be either ‘token <DEEPGRAM_API_KEY>’ or ‘Bearer <JWT_TOKEN>’
Query parameters
callbackstringOptional

URL to which we’ll make the callback request
callback_methodenumOptionalDefaults to POST

HTTP method by which the callback request will be made
Allowed values: POSTGETPUTDELETE
channelsstringOptionalDefaults to 1

The number of channels in the submitted audio
diarizebooleanOptional

Defaults to false. Recognize speaker changes. Each word in the transcript will be assigned a speaker number starting at 0
dictationenumOptionalDefaults to false

Identify and extract key entities from content in submitted audio
Allowed values: truefalse
encodingenumOptional

Specify the expected encoding of your submitted audio
linear16flacmulawamr-nbamr-wbopusspeexg729
endpointingstringOptionalDefaults to 10

Indicates how long Deepgram will wait to detect whether a speaker has finished speaking or pauses for a significant period of time. When set to a value, the streaming endpoint immediately finalizes the transcription for the processed time range and returns the transcript with a speech_final parameter set to true. Can also be set to false to disable endpointing
extrastringOptional

Arbitrary key-value pairs that are attached to the API response for usage in downstream processing
filler_wordsenumOptionalDefaults to false

Filler Words can help transcribe interruptions in your audio, like “uh” and “um”
Allowed values: truefalse
interim_resultsenumOptionalDefaults to false

Specifies whether the streaming endpoint should provide ongoing transcription updates as more audio is received. When set to true, the endpoint sends continuous updates, meaning transcription results may evolve over time
Allowed values: truefalse
keytermlist of stringsOptional

Key term prompting can boost or suppress specialized terminology and brands. Only compatible with Nova-3
keywordsstringOptional

Keywords can boost or suppress specialized terminology and brands
languageenumOptionalDefaults to en

The BCP-47 language tag

that hints at the primary spoken language. Depending on the Model you choose only certain languages are available
bgcacsdada-DKdede-CHelenen-AUen-GBen-INen-NZen-USeses-419es-LATAMetfifrfr-CAhihi-Latnhuiditjakoko-KRltlvmsnlnl-BEnoplptpt-BRpt-PTrorusksvsv-SEtaqthth-THtrukvizhzh-CNzh-HKzh-Hanszh-Hantzh-TW
modelenumOptional

AI model to use for the transcription
nova-3nova-3-generalnova-3-medicalnova-2nova-2-generalnova-2-meetingnova-2-financenova-2-conversationalainova-2-voicemailnova-2-videonova-2-medicalnova-2-drivethrunova-2-automotivenovanova-generalnova-phonecallnova-medicalenhancedenhanced-generalenhanced-meetingenhanced-phonecallenhanced-financebasemeetingphonecallfinanceconversationalaivoicemailvideocustom
multichannelenumOptionalDefaults to false

Transcribe each audio channel independently
Allowed values: truefalse
numeralsenumOptionalDefaults to false

Convert numbers from written format to numerical format
Allowed values: truefalse
profanity_filterenumOptionalDefaults to false

Profanity Filter looks for recognized profanity and converts it to the nearest recognized non-profane word or removes it from the transcript completely
Allowed values: truefalse
punctuateenumOptionalDefaults to false

Add punctuation and capitalization to the transcript
Allowed values: truefalse
redactenumOptionalDefaults to false

Redaction removes sensitive information from your transcripts
truefalsepcinumbersaggressive_numbersssn
replacestringOptional

Search for terms or phrases in submitted audio and replaces them
sample_ratestringOptional

Sample rate of submitted audio. Required (and only read) when a value is provided for encoding
searchstringOptional

Search for terms or phrases in submitted audio
smart_formatenumOptionalDefaults to false

Apply formatting to transcript output. When set to true, additional formatting will be applied to transcripts to improve readability
Allowed values: truefalse
tagstringOptional

Label your requests for the purpose of identification during usage reporting
utterance_endstringOptional

Indicates how long Deepgram will wait to send an UtteranceEnd message after a word has been transcribed. Use with interim_results
vad_eventsenumOptionalDefaults to false

Indicates that speech has started. You’ll begin receiving Speech Started messages upon speech starting
Allowed values: truefalse
versionstringOptionalDefaults to latest

Version of an AI model to use
Send
abc
transcriptionRequeststring
OR
listen_controlMessagesRequestobject
Finalize
type"Finalize"Required
OR
Close Stream
type"CloseStream"Required
OR
Keep Alive
type"KeepAlive"Required
Receive
transcriptionResponseobject
channelobjectOptional
alternativeslist of objectsOptional
metadataobjectOptional
model_infoobjectOptional
request_idstringOptional
format: "uuid"
model_uuidstringOptiAPI Reference
Speech to Text API
Live Audio

Deepgram Speech to Text WebSocket
Handshake
GET
Headers
AuthorizationstringRequired

API key for authentication. Format should be be either ‘token <DEEPGRAM_API_KEY>’ or ‘Bearer <JWT_TOKEN>’
Query parameters
callbackstringOptional

URL to which we’ll make the callback request
callback_methodenumOptionalDefaults to POST

HTTP method by which the callback request will be made
Allowed values: POSTGETPUTDELETE
channelsstringOptionalDefaults to 1

The number of channels in the submitted audio
diarizebooleanOptional

Defaults to false. Recognize speaker changes. Each word in the transcript will be assigned a speaker number starting at 0
dictationenumOptionalDefaults to false

Identify and extract key entities from content in submitted audio
Allowed values: truefalse
encodingenumOptional

Specify the expected encoding of your submitted audio
linear16flacmulawamr-nbamr-wbopusspeexg729
endpointingstringOptionalDefaults to 10

Indicates how long Deepgram will wait to detect whether a speaker has finished speaking or pauses for a significant period of time. When set to a value, the streaming endpoint immediately finalizes the transcription for the processed time range and returns the transcript with a speech_final parameter set to true. Can also be set to false to disable endpointing
extrastringOptional

Arbitrary key-value pairs that are attached to the API response for usage in downstream processing
filler_wordsenumOptionalDefaults to false

Filler Words can help transcribe interruptions in your audio, like “uh” and “um”
Allowed values: truefalse
interim_resultsenumOptionalDefaults to false

Specifies whether the streaming endpoint should provide ongoing transcription updates as more audio is received. When set to true, the endpoint sends continuous updates, meaning transcription results may evolve over time
Allowed values: truefalse
keytermlist of stringsOptional

Key term prompting can boost or suppress specialized terminology and brands. Only compatible with Nova-3
keywordsstringOptional

Keywords can boost or suppress specialized terminology and brands
languageenumOptionalDefaults to en

The BCP-47 language tag

that hints at the primary spoken language. Depending on the Model you choose only certain languages are available
bgcacsdada-DKdede-CHelenen-AUen-GBen-INen-NZen-USeses-419es-LATAMetfifrfr-CAhihi-Latnhuiditjakoko-KRltlvmsnlnl-BEnoplptpt-BRpt-PTrorusksvsv-SEtaqthth-THtrukvizhzh-CNzh-HKzh-Hanszh-Hantzh-TW
modelenumOptional

AI model to use for the transcription
nova-3nova-3-generalnova-3-medicalnova-2nova-2-generalnova-2-meetingnova-2-financenova-2-conversationalainova-2-voicemailnova-2-videonova-2-medicalnova-2-drivethrunova-2-automotivenovanova-generalnova-phonecallnova-medicalenhancedenhanced-generalenhanced-meetingenhanced-phonecallenhanced-financebasemeetingphonecallfinanceconversationalaivoicemailvideocustom
multichannelenumOptionalDefaults to false

Transcribe each audio channel independently
Allowed values: truefalse
numeralsenumOptionalDefaults to false

Convert numbers from written format to numerical format
Allowed values: truefalse
profanity_filterenumOptionalDefaults to false

Profanity Filter looks for recognized profanity and converts it to the nearest recognized non-profane word or removes it from the transcript completely
Allowed values: truefalse
punctuateenumOptionalDefaults to false

Add punctuation and capitalization to the transcript
Allowed values: truefalse
redactenumOptionalDefaults to false

Redaction removes sensitive information from your transcripts
truefalsepcinumbersaggressive_numbersssn
replacestringOptional

Search for terms or phrases in submitted audio and replaces them
sample_ratestringOptional

Sample rate of submitted audio. Required (and only read) when a value is provided for encoding
searchstringOptional

Search for terms or phrases in submitted audio
smart_formatenumOptionalDefaults to false

Apply formatting to transcript output. When set to true, additional formatting will be applied to transcripts to improve readability
Allowed values: truefalse
tagstringOptional

Label your requests for the purpose of identification during usage reporting
utterance_endstringOptional

Indicates how long Deepgram will wait to send an UtteranceEnd message after a word has been transcribed. Use with interim_results
vad_eventsenumOptionalDefaults to false

Indicates that speech has started. You’ll begin receiving Speech Started messages upon speech starting
Allowed values: truefalse
versionstringOptionalDefaults to latest

Version of an AI model to use
Send
abc
transcriptionRequeststring
OR
listen_controlMessagesRequestobject
Finalize
type"Finalize"Required
OR
Close Stream
type"CloseStream"Required
OR
Keep Alive
type"KeepAlive"Required
Receive
transcriptionResponseobject
channelobjectOptional
alternativeslist of objectsOptional
metadataobjectOptional
model_infoobjectOptional
request_idstringOptional
format: "uuid"
model_uuidstringOptional
format: "uuid"
typestringOptional
channel_indexlist of integersOptional
durationdoubleOptional
startdoubleOptional
is_finalbooleanOptional
from_finalizebooleanOptional
speech_finalbooleanOptional
OR
Control Message Response Zeroobject
type"Finalize"OptionalDefaults to Finalize
channelintegerOptional
>=0

The channel number being finalized
OR
Control Message Response Oneobject
type"Metadata"OptionalDefaults to Metadata
transaction_keystringOptional

Deprecated field
request_idstringOptional
format: "uuid"

Unique identifier for the request
sha256stringOptional
format: "^[a-fA-F0-9]{64}$"

SHA-256 hash of the audio content
createddatetimeOptional

Timestamp when the response was created
durationdoubleOptional

Duration of the audio in seconds
channelsintegerOptional
>=0

Number of audio channels
OR
Control Message Response Twoobject
type"CloseStream"OptionalDefaults to CloseStream
transaction_keystringOptional

Deprecated field
request_idstringOptional
format: "uuid"

Unique identifier for the request
sha256stringOptional
format: "^[a-fA-F0-9]{64}$"

SHA-256 hash of the audio content
createddatetimeOptional

Timestamp when the response was created
durationdoubleOptional

Duration of the audio in seconds
channelsintegerOptional
>=0

Number of audio channels
OR
listen_closeFrameobject
codeintegerRequired

WebSocket close status code
payloadenumRequired
Allowed values: NoneDATA-0000NET-0000NET-0001

Error reason code
Handshake
URL	wss://api.deepgram.com/v1/listen
Method	GET
Status	101 Switching Protocols
Messages
onal
format: "uuid"
typestringOptional
channel_indexlist of integersOptional
durationdoubleOptional
startdoubleOptional
is_finalbooleanOptional
from_finalizebooleanOptional
speech_finalbooleanOptional
OR
Control Message Response Zeroobject
type"Finalize"OptionalDefaults to Finalize
channelintegerOptional
>=0

The channel number being finalized
OR
Control Message Response Oneobject
type"Metadata"OptionalDefaults to Metadata
transaction_keystringOptional

Deprecated field
request_idstringOptional
format: "uuid"

Unique identifier for the request
sha256stringOptional
format: "^[a-fA-F0-9]{64}$"

SHA-256 hash of the audio content
createddatetimeOptional

Timestamp when the response was created
durationdoubleOptional

Duration of the audio in seconds
channelsintegerOptional
>=0

Number of audio channels
OR
Control Message Response Twoobject
type"CloseStream"OptionalDefaults to CloseStream
transaction_keystringOptional

Deprecated field
request_idstringOptional
format: "uuid"

Unique identifier for the request
sha256stringOptional
format: "^[a-fA-F0-9]{64}$"

SHA-256 hash of the audio content
createddatetimeOptional

Timestamp when the response was created
durationdoubleOptional

Duration of the audio in seconds
channelsintegerOptional
>=0

Number of audio channels
OR
listen_closeFrameobject
codeintegerRequired

WebSocket close status code
payloadenumRequired
Allowed values: NoneDATA-0000NET-0000NET-0001

Error reason code
Handshake
URL	wss://api.deepgram.com/v1/listen
Method	GET
Status	101 Switching Protocols
Messages
gOptional

Deprecated field
request_idstringOptional
format: "uuid"

Unique identifier for the request
sha256stringOptional
format: "^[a-fA-F0-9]{64}$"

SHA-256 hash of the audio content
createddatetimeOptional

Timestamp when the response was created
durationdoubleOptional

Duration of the audio in seconds
channelsintegerOptional
>=0

Number of audio channels
OR
Control Message Response Twoobject
type"CloseStream"OptionalDefaults to CloseStream
transaction_keystringOptional

Deprecated field
request_idstringOptional
format: "uuid"

Unique identifier for the request
sha256stringOptional
format: "^[a-fA-F0-9]{64}$"

SHA-256 hash of the audio content
createddatetimeOptional

Timestamp when the response was created
durationdoubleOptional

Duration of the audio in seconds
channelsintegerOptional
>=0

Number of audio channels
OR
listen_closeFrameobject
codeintegerRequired

WebSocket close status code
payloadenumRequired
Allowed values: NoneDATA-0000NET-0000NET-0001

Error reason code
Handshake
URL	wss://api.deepgram.com/v1/listen
Method	GET
Status	101 Switching Protocols
Messages
ncedenhanced-generalenhanced-meetingenhanced-phonecallenhanced-financebasemeetingphonecallfinanceconversationalaivoicemailvideocustom
multichannelenumOptionalDefaults to false

Transcribe each audio channel independently
Allowed values: truefalse
numeralsenumOptionalDefaults to false

Convert numbers from written format to numerical format
Allowed values: truefalse
profanity_filterenumOptionalDefaults to false

Profanity Filter looks for recognized profanity and converts it to the nearest recognized non-profane word or removes it from the transcript completely
Allowed values: truefalse
punctuateenumOptionalDefaults to false

Add punctuation and capitalization to the transcript
Allowed values: truefalse
redactenumOptionalDefaults to false

Redaction removes sensitive information from your transcripts
truefalsepcinumbersaggressive_numbersssn
replacestringOptional

Search for terms or phrases in submitted audio and replaces them
sample_ratestringOptional

Sample rate of submitted audio. Required (and only read) when a value is provided for encoding
searchstringOptional

Search for terms or phrases in submitted audio
smart_formatenumOptionalDefaults to false

Apply formatting to transcript output. When set to true, additional formatting will be applied to transcripts to improve readability
Allowed values: truefalse
tagstringOptional

Label your requests for the purpose of identification during usage reporting
utterance_endstringOptional

Indicates how long Deepgram will wait to send an UtteranceEnd message after a word has been transcribed. Use with interim_results
vad_eventsenumOptionalDefaults to false

Indicates that speech has started. You’ll begin receiving Speech Started messages upon speech starting
Allowed values: truefalse
versionstringOptionalDefaults to latest

Version of an AI model to use
Send
abc
transcriptionRequeststring
OR
listen_controlMessagesRequestobject
Finalize
type"Finalize"Required
OR
Close Stream
type"CloseStream"Required
OR
Keep Alive
type"KeepAlive"Required
Receive
transcriptionResponseobject
channelobjectOptional
alternativeslist of objectsOptional
metadataobjectOptional
model_infoobjectOptional
request_idstringOptional
format: "uuid"
model_uuidstringOptional
format: "uuid"
typestringOptional
channel_indexlist of integersOptional
durationdoubleOptional
startdoubleOptional
is_finalbooleanOptional
from_finalizebooleanOptional
speech_finalbooleanOptional
OR
Control Message Response Zeroobject
type"Finalize"OptionalDefaults to Finalize
channelintegerOptional
>=0

The channel number being finalized
OR
Control Message Response Oneobject
type"Metadata"OptionalDefaults to Metadata
transaction_keystringOptional

Deprecated field
request_idstringOptional
format: "uuid"

Unique identifier for the request
sha256stringOptional
format: "^[a-fA-F0-9]{64}$"

SHA-256 hash of the audio content
createddatetimeOptional

Timestamp when the response was created
durationdoubleOptional

Duration of the audio in seconds
channelsintegerOptional
>=0

Number of audio channels
OR
Control Message Response Twoobject
type"CloseStream"OptionalDefaults to CloseStream
transaction_keystringOptional

Deprecated field
request_idstringOptional
format: "uuid"

Unique identifier for the request
sha256stringOptional
format: "^[a-fA-F0-9]{64}$"

SHA-256 hash of the audio content
createddatetimeOptional

Timestamp when the response was created
durationdoubleOptional

Duration of the audio in seconds
channelsintegerOptional
>=0

Number of audio channels
OR
listen_closeFrameobject
codeintegerRequired

WebSocket close status code
payloadenumRequired
Allowed values: NoneDATA-0000NET-0000NET-0001

Error reason code
Handshake
URL	wss://api.deepgram.com/v1/listen
Method	GET
Status	101 Switching Protocols
Messages
