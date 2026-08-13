function nested_cell_index(varargin)
if nargin == 2
    job = varargin{1};
    flag = varargin{2};
    if ~isfield(job, 'config')
        job.config = default_config();
    end
    switch flag
        case 'run'
            files = job.images;
            reference = files{1};
            values = read_data(reference);
            if ~isempty(values)
                values(isnan(values)) = 0;
                selected = find(values ~= 0);
                for index = 1:length(selected)
                    values(:, index) = normalize(values(:, index));
                end
            end
    end
end
end
