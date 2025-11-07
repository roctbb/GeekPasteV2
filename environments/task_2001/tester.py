import wave
import numpy as np
import os

scenarios = [
    (1, 5),
    (2, 10)
]

comment_template = """
Результат:
{}

Ожидаемый результат:
{}

"""


def generate_random_audio_file(filename, channels, duration=10, sample_rate=44100):
    total_samples = duration

    # Generate random audio signal
    if channels == 1:
        signal = np.random.randint(-32768, 32767, total_samples, dtype=np.int16)
    elif channels == 2:
        signal = np.random.randint(-32768, 32767, total_samples * 2, dtype=np.int16)
    else:
        raise ValueError("Channels must be 1 (mono) or 2 (stereo)")

    with wave.open(filename, 'wb') as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)  # Number of bytes, 2 bytes for int16
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(signal.tobytes())


def reverse_audio_signal(signal, channels):
    if channels == 2:
        signal = signal.reshape(-1, 2)
        reversed_signal = signal[::-1].reshape(-1)
    else:
        reversed_signal = signal[::-1]
    return reversed_signal


def perform_tests(runner, source_code=None):
    for channels, points in scenarios:
        filename = "test_file.wav"

        generate_random_audio_file(filename, channels)

        input_data = f"{filename}\nresult.wav\n"
        runner(input_data, 5)

        with wave.open("result.wav", "rb") as result_wav_file:
            signal = result_wav_file.readframes(-1)
            print(len(signal))
            samples = np.frombuffer(signal, dtype=np.int16)

        with wave.open(filename, "rb") as input_wav_file:
            signal = input_wav_file.readframes(-1)
            reversed_signal = reverse_audio_signal(np.frombuffer(signal, dtype=np.int16), channels)

        if not np.array_equal(samples, reversed_signal):
            if channels == 1:
                return 1, "Не удалось развернуть моно файл." + comment_template.format(samples, reversed_signal)
            if channels == 2:
                return 5, "Неправильно развернут стерео файл." + comment_template.format(samples, reversed_signal)

    return 10, "OK! :)"


# Simulated runner to use the calculation function
def simulated_runner(user_input):
    input_file, output_file = user_input.strip().split('\n')
    with wave.open(input_file, 'rb') as wave_file:
        signal = wave_file.readframes(-1)
        signal = np.frombuffer(signal, dtype=np.int16).tolist()[::-1]
        params = wave_file.getparams()

    with wave.open(output_file, 'wb') as output_wav_file:
        output_wav_file.setparams(params)
        output_wav_file.writeframes(np.array(signal, dtype=np.int16).tobytes())


if __name__ == "__main__":
    points, comments = perform_tests(simulated_runner, None)
    print(comments)
