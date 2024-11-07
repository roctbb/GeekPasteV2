import wave
import numpy as np
import os

# Test scenarios: (channels, duration)
scenarios = [
    (1, 10),
    (2, 10)
]

comment_template = """
Исходный файл:
{}

Результат:
{}

Ожидаемый результат:
{}

"""


def generate_test_audio_file(filename, channels, duration=10, sample_rate=44100):
    total_samples = duration
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


def perform_tests(runner, source_code=None):
    for channels, duration in scenarios:
        filename = "task.wav"
        generate_test_audio_file(filename, channels, duration)

        # Test speeding up
        input_data = f"{filename}\nresult.wav\n1\n"
        runner(input_data)
        result, comments = validate_audio_transformation(filename, "result.wav", channels, 0.5, "ускорить")

        if not result and channels == 1:
            return 5, comments

        if not result and channels == 2:
            return 10, comments

        # Test slowing down
        input_data = f"{filename}\nresult.wav\n2\n"
        runner(input_data)
        result, comments = validate_audio_transformation(filename, "result.wav", channels, 2.0, "замедлить")

        if not result and channels == 1:
            return 5, comments
        if not result and channels == 2:
            return 12, comments


    return 15, "OK! :)"


def validate_audio_transformation(input_file, result_file, channels, speed_factor, mode):
    with wave.open(result_file, "rb") as result_wav_file:
        result_signal = result_wav_file.readframes(-1)
        result_samples = np.frombuffer(result_signal, dtype=np.int16)

    with wave.open(input_file, "rb") as input_wav_file:
        input_signal = input_wav_file.readframes(-1)
        input_samples = np.frombuffer(input_signal, dtype=np.int16)

        if channels == 2:
            input_samples = input_samples.reshape(-1, 2)

        if speed_factor < 1:  # Speeding up
            expected_samples = input_samples[::int(1 / speed_factor)]
        else:  # Slowing down
            expected_samples = np.repeat(input_samples, int(speed_factor), axis=0)

        # If mono, ensure we have the correct shape for comparison
        if channels == 2:
            expected_samples = expected_samples.reshape(-1)

    if not np.array_equal(result_samples, expected_samples):
        if channels == 1:
            return False, "Не удалось {mode} моно файл." + comment_template.format(np.frombuffer(input_signal, dtype=np.int16).tolist(), result_samples.tolist(), expected_samples.tolist())
        if channels == 2:
            return False, f"Не удалось {mode} стерео файл." + comment_template.format(np.frombuffer(input_signal, dtype=np.int16).tolist(), result_samples.tolist(),
                                                                                      expected_samples.tolist())

    return True, ""


# Simulated runner
def simulated_runner(user_input):
    input_file, output_file, mode = user_input.strip().split('\n')
    mode = int(mode)
    with wave.open(input_file, 'rb') as wave_file:
        signal = wave_file.readframes(-1)
        params = wave_file.getparams()
        original_signal = np.frombuffer(signal, dtype=np.int16)

    if wave_file.getnchannels() == 2:
        original_signal = original_signal.reshape(-1, 2)

    if mode == 1:  # Speeding up
        transformed_signal = original_signal[::2]
    elif mode == 2:  # Slowing down
        transformed_signal = np.repeat(original_signal, 2, axis=0)
    else:
        raise ValueError("Invalid mode. Use 1 to speed up and 2 to slow down.")

    # Flatten the signal for stereo if needed
    if wave_file.getnchannels() == 2:
        transformed_signal = transformed_signal.reshape(-1)

    with wave.open(output_file, 'wb') as output_wav_file:
        output_wav_file.setparams(params)
        output_wav_file.writeframes(transformed_signal.astype(np.int16).tobytes())


if __name__ == "__main__":
    points, comments = perform_tests(simulated_runner, None)
    print(points, comments)
