import wave
import numpy as np
import os

# Test scenarios
scenarios = [
    # (input_data, expected_output)
    ('task.wav', 'result.wav', 10)
]


def get_mean_loudness_from_signal(signal, channels):
    # If the audio is stereo, average the channels
    if channels == 2:
        signal = signal.reshape(-1, 2)
        signal = signal.mean(axis=1)
    # Compute mean loudness
    mean_loudness = np.mean(np.abs(signal))
    return mean_loudness


def get_mean_loudness_from_file(filename):
    with wave.open(filename, "rb") as wav_file:
        # Extract Raw Audio from Wav File
        signal = wav_file.readframes(-1)
        signal = np.frombuffer(signal, dtype=np.int16)
        # Get the number of channels
        channels = wav_file.getnchannels()
        return get_mean_loudness_from_signal(signal, channels)


def perform_tests(runner, source_code=None):
    for index, (input_file, output_file, level) in enumerate(scenarios):
        input_data = f"{input_file}\n{output_file}\n{level}\n"

        runner(input_data, 3)

        loudness_1 = get_mean_loudness_from_file("check.wav")
        loudness_2 = get_mean_loudness_from_file(output_file)

        if np.abs(loudness_1 - loudness_2) > 10:
            return 1, "Результат тише ожидаемого"
        if np.abs(loudness_1 - loudness_2) < -10:
            return 1, "Результат громче ожидаемого"
    return 5, "OK! :)"


# Simulated runner to use the calculation function
def simulated_runner(user_input, t=0):
    input_file, output_file, level = user_input.strip().split('\n')
    level = int(level)
    with wave.open(input_file, 'rb') as wave_file:
        signal = wave_file.readframes(-1)
        params = wave_file.getparams()

    samples = np.frombuffer(signal, dtype=np.int16).tolist()
    samples = [int(sample * level) for sample in samples]
    output_signal = np.array(samples, dtype=np.int16).tobytes()
    with wave.open(output_file, 'wb') as output_wav_file:
        output_wav_file.setparams(params)
        output_wav_file.writeframes(output_signal)

    return output_signal, params



if __name__ == "__main__":
    points, comments = perform_tests(simulated_runner, None)
    print(comments)
