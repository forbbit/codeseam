clear;
load input.mat
signal = raw(:, 1);
centered = signal - mean(signal);
scale = std(centered);
normalized = centered / scale;

accumulator = zeros(size(normalized));
for k = 2:length(normalized)
    accumulator(k) = 0.8 * accumulator(k - 1) + normalized(k);
end
blockSize = 64;
result = finalizeBlocks(accumulator, blockSize);
save output.mat result

function output = finalizeBlocks(input, blockSize)
count = floor(length(input) / blockSize);
output = zeros(size(input));
for block = 1:count
    first = (block - 1) * blockSize + 1;
    last = block * blockSize;
    segment = input(first:last);
    output(first:last) = segment - mean(segment);
end
end
