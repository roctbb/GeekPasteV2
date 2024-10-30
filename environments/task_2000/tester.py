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
        result_signal, params = runner(input_data)

        # Создание временного файла для использования с wave при необходимости
        temp_output_file = "temp_result.wav"
        with wave.open(temp_output_file, 'wb') as temp_wave_file:
            temp_wave_file.setparams(params)
            temp_wave_file.writeframes(result_signal)

        loudness_1 = get_mean_loudness_from_file("check.wav")
        loudness_2 = get_mean_loudness_from_file(temp_output_file)
        os.remove(temp_output_file)  # Удаляем временный файл

        if np.abs(loudness_1 - loudness_2) > 10:
            return 1, "Результат тише ожидаемого"
        if np.abs(loudness_1 - loudness_2) < -10:
            return 1, "Результат громче ожидаемого"
    return 5, "OK! :)"


# Simulated runner to use the calculation function
def simulated_runner(user_input):
    input_file, output_file, level = user_input.strip().split('\n')
    level = int(level)
    with wave.open(input_file, 'rb') as wave_file:
        signal = wave_file.readframes(-1)
        samples = np.frombuffer(signal, dtype=np.int16).tolist()
        samples = [int(sample * level) for sample in samples]
        params = wave_file.getparams()
        output_signal = np.array(samples, dtype=np.int16).tobytes()
        return output_signal, params


if __name__ == "__main__":
    points, comments = perform_tests(simulated_runner, None)
    print(comments)
