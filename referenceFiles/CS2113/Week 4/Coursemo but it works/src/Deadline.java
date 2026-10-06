public class Deadline extends Task {
    protected boolean isDone;
    protected String deadline;

    public Deadline(String description, String deadline) {
        super(description);
        this.deadline = deadline;
        isDone = false;
    }

    public boolean isDone() {
        return isDone;
    }

    public void setDone(boolean done) {
        isDone = done;
    }

    public String getBy() {
        return deadline;
    }

    public void setBy(String by) {
        deadline = by;
    }

    public String toString() {
        return super.toString() + System.lineSeparator()
                + "is done? " + (isDone ? "Yes" : "No") + System.lineSeparator()
                + "do by: " + deadline;
    }
}
