    public class Todo extends Task {
        protected boolean isDone;

        public Todo (String description) {
            super(description);
            isDone = false;
        }

        public boolean isDone() {
            return isDone;
        }

        public void setDone(boolean done) {
            isDone = done;
        }

    }
