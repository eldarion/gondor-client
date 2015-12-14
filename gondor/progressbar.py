import sys


class ProgressBar(object):
    """
    Creates a text-based progress bar. Call the object with the `print'
    command to see the progress bar, which looks something like this:

        [=======>        22%                  ]

    You may specify the progress bar's width, min and max values on init.
    """

    def __init__(self, minval=0, maxval=100, maxwidth=80):
        self.value = "[]"
        self.min = minval
        self.max = maxval
        self.span = maxval - minval
        self.width = maxwidth
        self.amount = 0
        self.update(0)

    def update(self, amount):
        """
        Update the progress bar with the new amount (with min and max
        values set at initialization; if it is over or under, it takes the
        min or max value as a default.
        """

        if amount < self.min:
            amount = self.min
        if amount > self.max:
            amount = self.max
        self.amount = amount

        # figure out the new percent done, round to an integer
        diff_from_min = float(self.amount - self.min)
        done = (diff_from_min / float(self.span)) * 100.0
        done = int(round(done))

        # figure out how many hash bars the percentage should be
        filled = self.width - 2
        num_hashes = (done / 100.0) * filled
        num_hashes = int(round(num_hashes))

        # Build a progress bar with an arrow of equal signs; special cases for
        # empty and full
        if num_hashes == 0:
            self.value = "[>{}]".format(" " * (filled - 1))
        elif num_hashes == filled:
            self.value = "[{}]".format("=" * filled)
        else:
            self.value = "[{}>{}]".format("=" * (num_hashes - 1), " " * (filled - num_hashes))

        # figure out where to put the percentage, roughly centered
        percent_offset = (len(self.value) // 2) - len(str(done))
        percent = "{}%".format(done)

        # slice the percentage into the bar
        self.value = "".join([
            self.value[0:percent_offset],
            percent,
            self.value[percent_offset + len(percent):]
        ])

    def display(self):
        sys.stdout.write("{}\r".format(self.value))
        sys.stdout.flush()
